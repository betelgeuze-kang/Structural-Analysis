# G1 True-Newton Load Sweep Status

- `summary_line`: `G1 true-Newton load sweep: PARTIAL | max_load=1.0 | full_load_descent=True | full_load_gate=False`
- `contract_pass`: `True`
- `evidence_closure_pass`: `False`
- `max_attempted_load_scale`: `1.0`
- `full_load_true_newton_final_residual_n`: `716.2398790963002`

| Load Scale | Steps | Initial Residual N | Final Residual N | Descent | Gate |
|---:|---:|---:|---:|---:|---:|
| `0.656` | `4` | `14643.949626859854` | `469.8533538138471` | `True` | `False` |
| `0.75` | `4` | `16742.320457537942` | `537.1799036113136` | `True` | `False` |
| `1.0` | `4` | `22323.093943383923` | `716.2398790963002` | `True` | `False` |

## Blockers

- `full_load_true_newton_residual_gate_not_passed`
- `full_load_checkpoint_not_created_by_true_newton_sweep`
- `production_rocm_hip_not_executed_by_true_newton_sweep`
- `full_mesh_nonlinear_equilibrium_not_proven_by_true_newton_sweep`

## Claim Boundary

This receipt records a non-promoting true-Newton load sweep. A full-load residual descent observation is not a G1 closure, not a full-load checkpoint, not full-mesh nonlinear equilibrium, and not production ROCm/HIP residual/JVP proof.
