# G1 True-Newton Full-Load Checkpoint Candidate Status

- `summary_line`: `G1 true-Newton full-load checkpoint candidate: CANDIDATE_CREATED | checkpoint_written=True | final_residual=650.47268272203 | residual_gate=False`
- `contract_pass`: `True`
- `evidence_closure_pass`: `False`
- `frame_tangent_source`: `force_based_residual_tangent`
- `checkpoint_path`: `implementation/phase1/release_evidence/productization/g1_true_newton_current450_force_frame_tangent_mu_0p003_diagnostic.npz`
- `checkpoint_schema`: `mgt-direct-residual-newton-state.v1`
- `checkpoint_load_scale`: `1.0`
- `steps`: `2`
- `final_residual_n`: `650.47268272203`
- `residual_gate_passed`: `False`

## Blockers

- `full_load_true_newton_checkpoint_residual_gate_not_passed`
- `production_rocm_hip_not_executed_by_true_newton_checkpoint_candidate`
- `full_mesh_nonlinear_equilibrium_not_proven_by_true_newton_checkpoint_candidate`
- `material_newton_breadth_not_proven_by_true_newton_checkpoint_candidate`

## Claim Boundary

This receipt creates a loadable full-load true-Newton checkpoint candidate. It is not a G1 closure and does not replace direct residual, increment, full-mesh nonlinear equilibrium, material Newton breadth, or production ROCm/HIP proof.
