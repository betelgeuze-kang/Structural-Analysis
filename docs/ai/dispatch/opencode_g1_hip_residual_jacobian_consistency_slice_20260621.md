# G1 HIP residual-Jacobian consistency slice

Goal: identify the smallest non-promoting change that moves `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py` toward a production ROCm/HIP residual-Jacobian consistency proof.

Scope:
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `tests/` files covering residual/Jacobian consistency or G1 HIP lane contracts
- `scripts/run_g1_full_load_hip_newton_lane.py` only if a child proof-intake field is needed

Constraints:
- Do not edit files.
- Do not mark existing CPU diagnostics, component-only receipts, reused evidence, or 0.656 checkpoints as G1 closure.
- Prefer metadata and explicit HIP-required blocked behavior over broad solver changes if the production HIP path is not available.
- Preserve current CLI behavior unless a new opt-in flag is proposed.

Deliverable:
- Name exact fields/flags/tests for an opt-in HIP-required consistency proof path.
- Say whether current receipts can satisfy it. If not, name the blocker.
- Keep output concise and limited to files/tests/blockers.
