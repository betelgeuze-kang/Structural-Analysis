# G1 Consistent Newton Full-Load Runner Contract

- `summary_line`: `G1 consistent Newton full-load runner contract: BLOCKED_RUNNER_CONTRACT | contract_pass=False | observed_load=1/1 | closure_blockers=20`
- `contract_pass`: `False`
- `evidence_closure_pass`: `False`
- `runner_id`: `build_consistent_newton_full_load_checkpoint_candidate_runner`
- `preferred_candidate_generator`: `consistent_residual_jacobian_newton_rocm_full_load_candidate`
- `observed_load`: `1.0`
- `required_load_scale`: `1.0`
- `true_newton_full_load_descent`: `True`
- `true_newton_full_load_gate`: `False`
- `true_newton_full_load_final_residual_n`: `716.2398790963002`
- `true_newton_checkpoint_candidate_written`: `True`
- `true_newton_checkpoint_candidate_residual_n`: `1558.2922733145824`
- `worker_path_ready`: `False`
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
- `checkpoint_direct_residual_inf_n`: `1558.2922733145824`

## Next Actions

- `promote_g1_assembly_contract_to_live_runner`: owner=`solver_numerics_owner`, status=`required`
- `generate_full_load_1p0_checkpoint_candidate`: owner=`g1_solver_owner`, status=`required`
- `close_consistent_residual_jacobian_newton_gate`: owner=`solver_numerics_owner`, status=`required`
- `prove_production_rocm_hip_residual_jvp_worker`: owner=`runtime_rocm_owner`, status=`required`

## Contract Blockers

- `production_rocm_hip_residual_jvp_worker_path_not_ready`

## Worker Path Repair Plan

- `next_action_id`: `repair_production_rocm_hip_residual_jvp_worker_path`
- `blocker_count`: `1`
- `matrix_free_global_krylov`: `1`

## Worker Path Operator Sequence

- `verify_rocm_runtime_device_interface`: owner=`runtime_rocm_owner`, status=`ready`
- `run_hip_required_direct_probe`: owner=`runtime_rocm_owner`, status=`required`
- `refresh_runner_contract_after_hip_probe`: owner=`g1_solver_owner`, status=`required`
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
- `hip_direct_probe::g1_fallback_zero_audit_not_closed`
- `hip_direct_probe::hip_residual_engine::matrix_free_global_krylov::accepted_state_tangent_refresh_not_hip`
- `hip_direct_probe::hip_residual_engine_contract_not_closed`
- `hip_direct_probe::regularized_fixed_point_residual_must_not_be_used_as_physical_residual`
- `hip_direct_probe_consistent_residual_jacobian_not_closed`
- `hip_direct_probe_fallback_zero_not_closed`
- `hip_direct_probe_hip_residual_engine_contract_not_closed`
- `hip_residual_engine::matrix_free_global_krylov::accepted_state_tangent_refresh_not_hip`
- `production_rocm_hip_residual_jvp_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `production_rocm_hip_residual_jvp_worker::global_krylov_accepted_state_tangent_refresh_hip_not_proven`
- `consistent_residual_jacobian_newton_gate_not_passed`
- `production_rocm_hip_worker_g1_closure_gate_not_ready`

## Claim Boundary

This packet defines the next G1 runner contract for generating a consistent residual/Jacobian Newton full-load checkpoint candidate. It does not create the checkpoint, close the consistent Newton gate, prove full-load 1.0 equilibrium, promote G1 closure, or allow an exhausted row-only support/link retuning loop to count as progress.
