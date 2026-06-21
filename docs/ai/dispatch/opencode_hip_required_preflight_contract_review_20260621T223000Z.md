# OpenCode Worker Slice: HIP-Required Preflight Contract Review

Goal: inspect the HIP-required residual/Jacobian consistency path and identify the smallest non-promoting test/guard that prevents CPU or incomplete HIP runtime from satisfying a production HIP proof.

Scope:
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `tests/test_mgt_residual_jacobian_consistency_probe.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py` only for `_rocm_hip_runtime_preflight` contract.

Questions:
- Does `require_hip_residual_engine=True` require a usable ROCm/HIP runtime before any CPU assembler path can run?
- Are `/dev/kfd`, `/dev/dri`, torch ROCm build, and `torch.cuda.is_available()` all represented in preflight evidence?
- Is there a missing regression test for "torch reports HIP available but required device nodes are absent" or for "preflight available but HIP residual/Jacobian implementation still cannot promote"?

Constraints:
- Do not edit files.
- Do not claim G1 closure.
- Do not synthesize ROCm/HIP evidence.
- Keep output limited to candidate files, tests, and blockers.
