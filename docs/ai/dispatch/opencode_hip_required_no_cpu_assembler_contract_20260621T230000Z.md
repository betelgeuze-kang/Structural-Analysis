# OpenCode Worker Slice: HIP-Required No-CPU Assembler Contract

Goal: review the HIP-required residual/Jacobian consistency path for CPU diagnostic leakage when `require_hip_residual_engine=True`.

Scope:
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `tests/test_mgt_residual_jacobian_consistency_probe.py`

Question:
- If `_rocm_hip_runtime_preflight()` returns `hip_available=true`, can the HIP-required path still call `build_direct_residual_assembler` before a production HIP residual/Jacobian implementation exists?

Constraints:
- Do not edit files.
- Do not claim G1 closure.
- Keep output limited to candidate guard/test and blockers.
