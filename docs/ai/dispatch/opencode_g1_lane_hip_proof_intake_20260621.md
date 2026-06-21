# G1 lane HIP residual/Jacobian proof-intake slice

Goal: identify the smallest non-promoting change to make scripts/run_g1_full_load_hip_newton_lane.py consume the separate HIP-required residual/Jacobian consistency receipt.

Scope:
- scripts/run_g1_full_load_hip_newton_lane.py
- tests/test_run_g1_full_load_hip_newton_lane.py
- implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json only as an input contract reference

Constraints:
- Do not edit files.
- Do not promote 0.656 checkpoint, CPU diagnostic consistency, partial HIP-required receipt, or reused evidence to G1 closure.
- Preserve dry-run behavior except for reporting the new proof requirement.
- The lane should remain blocked unless the external HIP-required receipt has source_commit_sha matching lane source, reused_evidence=false, rocm_hip_required=true, consistent_residual_jacobian_newton_gate_passed=true, and no blockers.

Deliverable:
- Name exact fields, blockers, and tests for this proof-intake change.
- Keep output concise.
