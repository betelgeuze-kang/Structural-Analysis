# G1 Consistent Newton Full-Load Runner Contract

- `summary_line`: `G1 consistent Newton full-load runner contract: READY_FOR_RUNNER_IMPLEMENTATION | contract_pass=True | observed_load=1/1 | closure_blockers=13`
- `contract_pass`: `True`
- `evidence_closure_pass`: `False`
- `runner_id`: `build_consistent_newton_full_load_checkpoint_candidate_runner`
- `preferred_candidate_generator`: `consistent_residual_jacobian_newton_rocm_full_load_candidate`
- `observed_load`: `1.0`
- `required_load_scale`: `1.0`
- `true_newton_full_load_descent`: `True`
- `true_newton_full_load_gate`: `False`
- `true_newton_full_load_final_residual_n`: `716.2398790963002`
- `true_newton_checkpoint_candidate_written`: `True`
- `true_newton_checkpoint_candidate_residual_n`: `655.1039650392886`
- `true_newton_from_active_set_final_residual_n`: `0.42740724991695345`
- `true_newton_from_active_set_stop_reason`: `line_search_no_descent`
- `true_newton_from_active_set_max_jvp_gap_relative_inf`: `4.088178091005261`
- `true_newton_service_tangent_max_jvp_gap_relative_inf`: `4.088231545444302`
- `true_newton_frame_tangent_comparison_both_frame_gap`: `True`
- `frame_tangent_fd_epsilon_sweep_default_gap_relative_inf`: `4.088178091005261`
- `frame_tangent_fd_epsilon_sweep_best_gap_relative_inf`: `0.003379869645939948`
- `frame_tangent_fd_epsilon_sweep_default_eps_artifact_likely`: `True`
- `true_newton_mu_sweep_descent_observed`: `False`
- `true_newton_mu_sweep_best_mu`: `0.03`
- `true_newton_mu_sweep_best_improvement_inf_n`: `-2.9530156098189764e-10`
- `load_parameter_probe_descent_observed`: `False`
- `load_parameter_tiny_trust_descent_observed`: `True`
- `load_parameter_tiny_trust_best_load_scale`: `0.99999`
- `load_parameter_tiny_trust_restored_full_load_descent`: `False`
- `active_frontier_residual_ownership_top_row_balance_driver`: `external_load_balance`
- `active_frontier_residual_ownership_top_row_component`: `shell_bending_drilling`
- `active_frontier_residual_ownership_top_row_external_load_n`: `0.569876333333335`
- `active_frontier_shell_load_required_scale`: `0.25000000014572954`
- `active_frontier_shell_load_free_pressure_resultant`: `True`
- `active_frontier_shell_load_top_element_id`: `25880`
- `active_frontier_shell_policy_best_policy`: `attached_components_only`
- `active_frontier_shell_policy_best_residual_n`: `0.3818403374023447`
- `active_frontier_shell_policy_descent_observed`: `True`
- `active_frontier_shell_policy_linearized_best_after_n`: `7.245315458703772e-13`
- `active_frontier_shell_policy_linearized_direct_replay_required`: `True`
- `active_frontier_structural_policy_active_set_final_residual_n`: `0.07205501101467937`
- `active_frontier_structural_policy_active_set_alpha_sweep_stop`: `no_candidate_descent`
- `active_frontier_structural_policy_top_component`: `shell_bending_drilling`
- `active_frontier_structural_policy_top_balance_driver`: `shell_bending_drilling_internal_force`
- `active_frontier_shell_rotation_candidate_residual_n`: `0.04728610099315822`
- `active_frontier_shell_rotation_no_descent`: `False`
- `adaptive_all_components_frontier_final_residual_n`: `0.4278304040181992`
- `adaptive_all_components_frontier_gate`: `False`
- `shell_hotspot_tangent_fd_jvp_consistent`: `True`
- `shell_hotspot_diagonal_sweep_descent`: `False`
- `global_tangent_scaled_sweep_descent`: `False`
- `residual_norm_gradient_l2_descent`: `True`
- `residual_norm_gradient_inf_descent`: `False`
- `active_set_ls_full_inf_descent`: `True`
- `active_set_ls_best_full_residual_n`: `0.4274072503950392`
- `active_set_ls_trust_candidate_final_residual_n`: `0.42740724991695345`
- `active_set_ls_trust_candidate_gate`: `False`
- `active_set_ls_schedule_final_residual_n`: `0.4274072499174437`
- `active_set_ls_tangent_fd_jvp_consistent`: `True`
- `active_set_ls_tangent_fd_jvp_max_relative_inf_error`: `4.753647244794899e-14`
- `active_set_minimax_final_residual_n`: `0.42740724991695345`
- `active_set_minimax_steps_taken`: `0`
- `worker_path_ready`: `True`
- `worker_g1_closure_gate_ready`: `False`
- `assembly_contract_seed_ready`: `True`
- `cpu_seed_newton_parity`: `True`

## Acceptance Criteria

- `g1_assembly_contract_seed_report_contract_passes`
- `cpu_seed_direct_residual_newton_parity_passes`
- `live_g1_runner_uses_assembly_result_residual_jacobian_contract`
- `loadable_checkpoint_schema_mgt_direct_residual_newton_state_v1`
- `checkpoint_load_scale_gte_1p0`
- `no_load_path_provenance_contradiction`
- `direct_residual_gate_passes_without_regularized_fixed_point_substitute`
- `consistent_residual_jacobian_newton_gate_passes`
- `production_rocm_hip_residual_jvp_worker_has_no_cpu_fallback`
- `device_resident_residual_jvp_rows_retained`
- `g1_full_load_hip_newton_lane_report_contract_passes_after_rerun`

## True-Newton Load Sweep

- `present`: `True`
- `status`: `partial`
- `max_attempted_load_scale`: `1.0`
- `full_load_true_newton_residual_descent_observed`: `True`
- `full_load_true_newton_residual_gate_passed`: `False`

## True-Newton Checkpoint Candidate

- `present`: `True`
- `status`: `candidate_created`
- `checkpoint_written`: `True`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_true_newton_full_load_checkpoint_candidate.npz`
- `checkpoint_direct_residual_inf_n`: `655.1039650392886`

## True-Newton From Active-Set Frontier

- `present`: `True`
- `status`: `review`
- `stop_reason`: `line_search_no_descent`
- `true_final_residual_n`: `0.42740724991695345`
- `max_jvp_minus_unregularized_tangent_action_relative_inf`: `4.088178091005261`
- `dominant_jvp_gap_component`: `frame`

## True-Newton Service-Tangent From Active-Set Frontier

- `present`: `True`
- `status`: `review`
- `stop_reason`: `line_search_no_descent`
- `true_final_residual_n`: `0.42740724991695345`
- `max_jvp_minus_unregularized_tangent_action_relative_inf`: `4.088231545444302`
- `dominant_jvp_gap_component`: `frame`

## Frame Tangent Source Comparison

- `present`: `True`
- `both_line_search_no_descent`: `True`
- `both_dominant_gap_component_frame`: `True`
- `service_minus_force_max_jvp_gap_relative_inf`: `5.3454439040478974e-05`

## Frame Tangent FD Epsilon Sweep

- `present`: `True`
- `default_jvp_eps`: `1e-06`
- `default_eps_gap_relative_inf`: `4.088178091005261`
- `best_eps`: `0.001`
- `best_eps_gap_relative_inf`: `0.003379869645939948`
- `default_eps_artifact_likely`: `True`

## True-Newton Mu Sweep From Active-Set Frontier

- `present`: `True`
- `evaluated_mu_count`: `11`
- `factorable_mu_count`: `11`
- `descent_observed`: `False`
- `best_mu`: `0.03`
- `best_residual_inf_n`: `0.427407250212255`
- `best_improvement_inf_n`: `-2.9530156098189764e-10`

## Active-Set Load-Parameter Probe

- `present`: `True`
- `actual_replay_descent_observed`: `False`
- `best_actual_replay_load_scale`: `0.995`
- `best_actual_replay_residual_inf_n`: `66.12257730630517`
- `best_actual_replay_improvement_inf_n`: `-65.69517005638822`
- `restored_full_load_descent_observed`: `False`
- `best_restored_full_load_residual_inf_n`: `0.42811959570077285`

## Active-Set Load-Parameter Tiny-Trust Probe

- `present`: `True`
- `actual_replay_descent_observed`: `True`
- `best_actual_replay_load_scale`: `0.99999`
- `best_actual_replay_residual_inf_n`: `0.4274029760383601`
- `best_actual_replay_improvement_inf_n`: `4.273878593363811e-06`
- `restored_full_load_descent_observed`: `False`
- `best_restored_full_load_residual_inf_n`: `0.42740796265036174`

## Active Frontier Residual Ownership

- `present`: `True`
- `top_residual_inf_n`: `0.42740724991695345`
- `top_row_node_id`: `2276`
- `top_row_dof_label`: `UZ`
- `top_row_dominant_internal_component`: `shell_bending_drilling`
- `top_row_balance_driver`: `external_load_balance`
- `top_row_inferred_external_load_n`: `0.569876333333335`
- `top_row_load_derivative_n_per_load`: `-0.5698763333333301`

## Active Frontier Shell Load Neighborhood

- `present`: `True`
- `top_row_required_reference_shell_load_scale_for_zero_row_residual`: `0.25000000014572954`
- `top_row_shell_internal_to_reference_load_scale`: `0.2500000001903663`
- `top_row_surface_component_free_pressure_resultant`: `True`
- `top_row_incident_surface_element_count`: `1`
- `top_row_surface_component_frame_connected_node_count`: `0`
- `top_incident_element_id`: `25880`

## Active Frontier Shell Policy Replay

- `present`: `True`
- `baseline_policy`: `all_components`
- `baseline_residual_inf_n`: `0.42740724991695345`
- `best_policy`: `attached_components_only`
- `best_residual_inf_n`: `0.3818403374023447`
- `best_improvement_inf_n`: `0.04556691251460876`
- `structural_or_attached_policy_descent_observed`: `True`
- `best_policy_pressure_suppressed_surface_element_count`: `2`
- `best_residual_gate_passed`: `False`

## Active Frontier Shell Policy Linearized Active-Set

- `present`: `True`
- `shell_pressure_load_path_policy`: `structural_components_only`
- `base_residual_inf_n`: `0.3818403374023447`
- `best_active_row_count`: `8`
- `best_linear_active_residual_after_inf_n`: `7.245315458703772e-13`
- `best_linear_active_improvement_inf_n`: `0.38184033740162016`
- `linearized_active_descent_observed`: `True`
- `direct_replay_required_for_candidate`: `True`

## Active Frontier Structural Policy Active-Set LS Trust

- `present`: `True`
- `shell_pressure_load_path_policy`: `structural_components_only`
- `initial_residual_n`: `0.12093228075045737`
- `final_residual_n`: `0.07205501101467937`
- `total_reduction_n`: `0.048877269735777995`
- `total_reduction_ratio`: `0.4041705773881482`
- `residual_gate_passed`: `False`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz`

## Active Frontier Structural Policy Alpha Sweep

- `present`: `True`
- `stop_reason`: `no_candidate_descent`
- `final_residual_n`: `0.07205501101467937`

## Active Frontier Structural Policy Residual Ownership

- `present`: `True`
- `top_residual_inf_n`: `0.07205501101467937`
- `top_row_node_id`: `2274`
- `top_row_dof_label`: `RX`
- `top_row_dominant_internal_component`: `shell_bending_drilling`
- `top_row_balance_driver`: `shell_bending_drilling_internal_force`
- `top_row_inferred_external_load_n`: `0.0`
- `top_row_load_derivative_n_per_load`: `0.0`

## Active Frontier Structural Policy Linearized After Two-Step

- `best_linear_active_residual_after_inf_n`: `3.396605913197348e-13`
- `linearized_active_descent_observed`: `True`
- `direct_replay_required_for_candidate`: `True`

## Active Frontier Shell Rotation Row Candidate

- `present`: `True`
- `fd_consistent`: `True`
- `selected_rotation_row_count`: `4`
- `best_direct_residual_inf_n`: `0.04728610099315822`
- `best_improvement_inf_n`: `0.006755157257430255`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz`
- `checkpoint_best_alpha`: `0.125`

## Active Frontier Shell Rotation Row No-Descent Probe

- `present`: `True`
- `base_residual_inf_n`: `0.04728610099315822`
- `best_improvement_inf_n`: `-0.0016700968262350901`
- `direct_descent_observed`: `False`

## Active Frontier Shell Rotation Candidate Residual Ownership

- `top_residual_inf_n`: `0.04728610099315822`
- `top_row_dof_label`: `RX`
- `top_row_dominant_internal_component`: `shell_bending_drilling`
- `top_row_balance_driver`: `shell_bending_drilling_internal_force`

## Sparse Direct Scaled-LSMR Frontier Probe

- `present`: `True`
- `status`: `ready`
- `jvp_parity_pass`: `True`
- `assembled_tangent_parity_pass`: `True`
- `direction_status`: `ready`
- `direction_iterations`: `27`
- `line_search_status`: `ready`
- `line_search_residual_after_n`: `0.04728606850215522`
- `line_search_residual_reduction_ratio`: `6.871152900485691e-07`
- `output_checkpoint_written`: `True`
- `output_checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz`
- `output_checkpoint_direct_residual_inf_n`: `0.04728606850215522`
- `output_checkpoint_residual_gate_passed`: `False`

## Sparse Direct Scaled-LSMR Second Step Probe

- `present`: `True`
- `status`: `ready`
- `line_search_status`: `ready`
- `line_search_residual_after_n`: `0.047285916814733264`
- `line_search_residual_reduction_ratio`: `3.2078670687026466e-06`
- `output_checkpoint_written`: `True`
- `output_checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz`
- `output_checkpoint_direct_residual_inf_n`: `0.047285916814733264`
- `output_checkpoint_residual_gate_passed`: `False`

## Sparse Direct Scaled-LSMR Accepted-Step Chain

- `step_count`: `3`
- `ready_step_count`: `3`
- `monotonic_residual_descent`: `True`
- `initial_residual_n`: `0.04728610099315822`
- `final_residual_n`: `0.047285863685509466`
- `total_reduction_n`: `2.3730764875384835e-07`
- `total_reduction_ratio`: `5.018549716928113e-06`
- `latest_checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz`
- `latest_checkpoint_residual_gate_passed`: `False`

## Sparse Direct Scaled-LSMR Chain Receipt

- `path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_chain_probe.json`
- `status`: `ready`
- `final_residual_n`: `0.047285863685509466`
- `latest_checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_chain_step_03_candidate.npz`

## Sparse Direct Scaled-LSMR Long-Chain Receipt

- `path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_long_chain_probe.json`
- `status`: `ready`
- `step_count`: `10`
- `final_residual_n`: `0.04728560329011722`
- `final_residual_over_gate`: `94.57120658023443`
- `estimated_steps_to_gate_at_last_reduction`: `2008386`
- `gate_convergence_assessment`: `stalled_for_gate`
- `recommended_next_action`: `switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain`
- `latest_checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz`

## Adaptive All-Components Frontier

- `present`: `True`
- `status`: `review`
- `shell_pressure_load_path_policy`: `all_components`
- `final_residual_n`: `0.4278304040181992`
- `residual_gate_passed`: `False`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_adaptive_fixed_signed_all_components_from_structural_60step_diagnostic.npz`

## Shell Hotspot Narrowing

- `jvp_present`: `True`
- `jvp_fd_consistent`: `True`
- `jvp_max_relative_inf_error`: `8.335535780253022e-14`
- `diagonal_present`: `True`
- `diagonal_descent_observed`: `False`
- `diagonal_best_direct_residual_inf_n`: `0.4278508811240626`
- `diagonal_best_improvement_inf_n`: `-2.0477105863392353e-05`

## Global Tangent Sweep

- `present`: `True`
- `evaluated`: `True`
- `scaling_mode`: `row_col_inf`
- `descent_observed`: `False`
- `linear_relative_residual_inf`: `0.4278305011820284`
- `best_direct_residual_inf_n`: `0.42783040426657654`
- `best_improvement_inf_n`: `-2.483773187123006e-10`

## Residual-Norm Gradient Sweep

- `present`: `True`
- `evaluated`: `True`
- `trust_radius_m`: `1e-15`
- `inf_descent_observed`: `False`
- `l2_descent_observed`: `True`
- `best_l2_direct_residual_l2_n`: `1.2159739821333575`
- `best_l2_improvement_l2_n`: `0.16379561248899166`

## Active-Set LS Sweep

- `present`: `True`
- `evaluated`: `True`
- `selected_hotspot_row_count`: `8`
- `full_inf_descent_observed`: `True`
- `active_inf_descent_observed`: `True`
- `best_full_direct_residual_inf_n`: `0.4274072503950392`
- `best_full_improvement_inf_n`: `0.000423153623160033`

## Active-Set LS Trust Candidate

- `present`: `True`
- `status`: `candidate_created`
- `checkpoint_written`: `True`
- `final_residual_n`: `0.42740724991695345`
- `total_reduction_n`: `0.0004231541012457707`
- `residual_gate_passed`: `False`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz`

## Active-Set LS Schedule Candidate

- `present`: `True`
- `status`: `candidate_created`
- `active_row_count_schedule`: `[8, 16, 32]`
- `final_residual_n`: `0.4274072499174437`
- `total_reduction_n`: `0.0004231541007554962`

## Active-Set Trust Tangent FD JVP

- `present`: `True`
- `fd_consistent`: `True`
- `evaluated_row_count`: `2`
- `max_relative_inf_error`: `4.753647244794899e-14`
- `max_relative_l2_error`: `3.717340984475282e-14`

## Active-Set Minimax Trust Candidate

- `present`: `True`
- `status`: `review`
- `final_residual_n`: `0.42740724991695345`
- `total_reduction_n`: `0.0`
- `steps_taken`: `0`
- `best_linear_active_inf_improvement_n`: `1.1784706543949142e-10`

## Next Actions

- `promote_g1_assembly_contract_to_live_runner`: owner=`solver_numerics_owner`, status=`required`
- `generate_full_load_1p0_checkpoint_candidate`: owner=`g1_solver_owner`, status=`required`
- `close_consistent_residual_jacobian_newton_gate`: owner=`solver_numerics_owner`, status=`required`
- `prove_production_rocm_hip_residual_jvp_worker`: owner=`runtime_rocm_owner`, status=`required`

## Worker Path Repair Plan

- `next_action_id`: `rerun_g1_full_load_hip_newton_lane`
- `blocker_count`: `0`

## Worker Path Operator Sequence

- `verify_rocm_runtime_device_interface`: owner=`runtime_rocm_owner`, status=`ready`
- `run_hip_required_direct_probe`: owner=`runtime_rocm_owner`, status=`ready`
- `refresh_runner_contract_after_hip_probe`: owner=`g1_solver_owner`, status=`ready`
- `rerun_g1_full_load_lane_with_full_load_checkpoint`: owner=`g1_solver_owner`, status=`required`

## Closure Blockers

- `hip_consistency_proof_gate_not_passed`
- `hip_consistency_proof_worker_g1_closure_gate_not_ready`
- `hip_consistency_proof_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `hip_consistency_proof_has_blockers`
- `consistent_residual_jacobian::consistent_residual_jacobian_newton_not_proven`
- `consistent_residual_jacobian::state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency`
- `hip_direct_probe::consistent_jacobian_or_globalization_required`
- `hip_direct_probe::direct_residual_gate_not_closed`
- `hip_direct_probe::regularized_fixed_point_residual_must_not_be_used_as_physical_residual`
- `hip_direct_probe_consistent_residual_jacobian_not_closed`
- `production_rocm_hip_residual_jvp_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `consistent_residual_jacobian_newton_gate_not_passed`
- `production_rocm_hip_worker_g1_closure_gate_not_ready`

## Claim Boundary

This packet defines the next G1 runner contract for generating a consistent residual/Jacobian Newton full-load checkpoint candidate. It does not create the checkpoint, close the consistent Newton gate, prove full-load 1.0 equilibrium, promote G1 closure, or allow an exhausted row-only support/link retuning loop to count as progress.
