# G1 child consistent-Jacobian contract probe

Goal: identify the smallest release-lane contract change that makes `scripts/run_g1_full_load_hip_newton_lane.py` require explicit child proof of consistent residual/Jacobian Newton closure, without treating diagnostic Jacobian flags as closure.

Scope:
- `scripts/run_g1_full_load_hip_newton_lane.py`
- `tests/test_run_g1_full_load_hip_newton_lane.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`

Constraints:
- Do not edit files.
- Do not promote existing 0.656 checkpoint, reused evidence, CPU diagnostics, or matrix-free diagnostic inclusion flags to G1 closure.
- Keep existing HIP residual, material Newton breadth, fallback-zero, and full-load child safety requirements.
- Prefer one explicit blocker name for missing child consistent-Jacobian proof.

Deliverable:
- List the child payload fields that would be safe to require as explicit proof.
- If no current field is authoritative enough, propose a conservative new safety blocker and focused tests.
- Keep output to changed-file/test/blocker terminology only.
