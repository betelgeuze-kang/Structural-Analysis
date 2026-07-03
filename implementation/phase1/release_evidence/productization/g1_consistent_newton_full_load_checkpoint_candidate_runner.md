# G1 Consistent Newton Full-Load Runner Contract

- `summary_line`: `G1 consistent Newton full-load runner contract: BLOCKED_RUNNER_CONTRACT | contract_pass=False | observed_load=0.656/1 | closure_blockers=27`
- `contract_pass`: `False`
- `evidence_closure_pass`: `False`
- `runner_id`: `build_consistent_newton_full_load_checkpoint_candidate_runner`
- `preferred_candidate_generator`: `consistent_residual_jacobian_newton_rocm_full_load_candidate`
- `observed_load`: `0.656`
- `required_load_scale`: `1.0`
- `worker_path_ready`: `False`
- `worker_g1_closure_gate_ready`: `False`

## Acceptance Criteria

- `loadable_checkpoint_schema_mgt_direct_residual_newton_state_v1`
- `checkpoint_load_scale_gte_1p0`
- `no_load_path_provenance_contradiction`
- `direct_residual_gate_passes_without_regularized_fixed_point_substitute`
- `consistent_residual_jacobian_newton_gate_passes`
- `production_rocm_hip_residual_jvp_worker_has_no_cpu_fallback`
- `device_resident_residual_jvp_rows_retained`
- `g1_full_load_hip_newton_lane_report_contract_passes_after_rerun`

## Next Actions

- `generate_full_load_1p0_checkpoint_candidate`: owner=`g1_solver_owner`, status=`required`
- `close_consistent_residual_jacobian_newton_gate`: owner=`solver_numerics_owner`, status=`required`
- `prove_production_rocm_hip_residual_jvp_worker`: owner=`runtime_rocm_owner`, status=`required`

## Contract Blockers

- `production_rocm_hip_residual_jvp_worker_path_not_ready`

## Worker Path Repair Plan

- `next_action_id`: `repair_production_rocm_hip_residual_jvp_worker_path`
- `blocker_count`: `9`
- `runtime_device_interface`: `3`
- `hip_required_direct_probe`: `1`
- `production_hip_residual_jacobian_path`: `1`
- `matrix_free_global_krylov`: `3`
- `current_tangent_residual_row_replay`: `1`

## Worker Path Operator Sequence

- `verify_rocm_runtime_device_interface`: owner=`runtime_rocm_owner`, status=`required`
- `run_hip_required_direct_probe`: owner=`runtime_rocm_owner`, status=`required`
- `refresh_runner_contract_after_hip_probe`: owner=`g1_solver_owner`, status=`required`
- `rerun_g1_full_load_lane_with_full_load_checkpoint`: owner=`g1_solver_owner`, status=`required`

## Closure Blockers

- `checkpoint_load_scale_below_required_full_load`
- `checkpoint_resolution_no_full_load_candidate`
- `hip_consistency_proof_production_hip_path_not_proven`
- `hip_consistency_proof_gate_not_passed`
- `hip_consistency_proof_residual_jvp_worker_path_not_ready`
- `hip_consistency_proof_worker_g1_closure_gate_not_ready`
- `hip_consistency_proof_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `hip_consistency_proof_worker::current_tangent_residual_row_hip_replay_not_proven`
- `hip_consistency_proof_worker::direct_probe_not_executed_preflight_only`
- `hip_consistency_proof_worker::global_krylov_accepted_state_tangent_refresh_hip_not_proven`
- `hip_consistency_proof_worker::global_krylov_hip_solver_not_proven`
- `hip_consistency_proof_worker::global_krylov_jvp_rows_not_retained`
- `hip_consistency_proof_worker::production_hip_residual_jacobian_path_not_proven`
- `hip_consistency_proof_worker::rocm_hip_runtime_unavailable`
- `hip_consistency_proof_worker::runtime::dev_dri_missing`
- `hip_consistency_proof_worker::runtime::dev_kfd_missing`
- `hip_consistency_proof_has_blockers`
- `hip_consistency_proof_runtime::dev_kfd_missing`
- `hip_consistency_proof_runtime::dev_dri_missing`
- `rocm_hip_runtime_unavailable`
- `hip_runtime::dev_kfd_missing`
- `hip_runtime::dev_dri_missing`
- `hip_residual_jacobian_consistency_preflight_only`
- `hip_residual_jacobian_consistency_not_executed`
- `full_load_checkpoint_1p0_not_available`
- `consistent_residual_jacobian_newton_gate_not_passed`
- `production_rocm_hip_worker_g1_closure_gate_not_ready`

## Claim Boundary

This packet defines the next G1 runner contract for generating a consistent residual/Jacobian Newton full-load checkpoint candidate. It does not create the checkpoint, close the consistent Newton gate, prove full-load 1.0 equilibrium, promote G1 closure, or allow an exhausted row-only support/link retuning loop to count as progress.
