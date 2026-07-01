# G1 Consistent Newton Full-Load Runner Contract

- `summary_line`: `G1 consistent Newton full-load runner contract: READY_FOR_RUNNER_IMPLEMENTATION | contract_pass=True | observed_load=0.656/1 | closure_blockers=17`
- `contract_pass`: `True`
- `evidence_closure_pass`: `False`
- `runner_id`: `build_consistent_newton_full_load_checkpoint_candidate_runner`
- `preferred_candidate_generator`: `consistent_residual_jacobian_newton_rocm_full_load_candidate`
- `observed_load`: `0.656`
- `required_load_scale`: `1.0`
- `worker_path_ready`: `True`
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

## Closure Blockers

- `checkpoint_load_scale_below_required_full_load`
- `checkpoint_resolution_no_full_load_candidate`
- `hip_consistency_proof_gate_not_passed`
- `hip_consistency_proof_worker_g1_closure_gate_not_ready`
- `hip_consistency_proof_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `hip_consistency_proof_has_blockers`
- `consistent_residual_jacobian::consistent_residual_jacobian_newton_not_proven`
- `consistent_residual_jacobian::state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency`
- `hip_direct_probe::consistent_jacobian_or_globalization_required`
- `hip_direct_probe::direct_residual_gate_not_closed`
- `hip_direct_probe::full_load_gate_not_closed`
- `hip_direct_probe::regularized_fixed_point_residual_must_not_be_used_as_physical_residual`
- `hip_direct_probe_consistent_residual_jacobian_not_closed`
- `production_rocm_hip_residual_jvp_worker::consistent_residual_jacobian_newton_gate_not_passed`
- `full_load_checkpoint_1p0_not_available`
- `consistent_residual_jacobian_newton_gate_not_passed`
- `production_rocm_hip_worker_g1_closure_gate_not_ready`

## Claim Boundary

This packet defines the next G1 runner contract for generating a consistent residual/Jacobian Newton full-load checkpoint candidate. It does not create the checkpoint, close the consistent Newton gate, prove full-load 1.0 equilibrium, promote G1 closure, or allow an exhausted row-only support/link retuning loop to count as progress.
