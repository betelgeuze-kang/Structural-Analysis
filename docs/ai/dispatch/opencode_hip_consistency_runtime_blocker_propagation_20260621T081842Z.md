# OpenCode task: HIP consistency runtime blocker propagation

## Goal
Check whether the HIP-required residual/Jacobian consistency receipt should propagate ROCm/HIP runtime blockers into its top-level `blockers` list.

## Scope
- Inspect only:
  - `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
  - `tests/test_mgt_residual_jacobian_consistency_probe.py`
  - `implementation/phase1/run_mgt_direct_residual_newton_probe.py` only for preflight field shape
- Do not edit release receipts, README, ledgers, or UI files.

## Constraints
- Do not mark HIP/G1 ready.
- Do not synthesize ROCm/HIP evidence.
- Do not relax thresholds or remove existing blockers.
- Preserve the current behavior that HIP-required mode exits blocked/partial without CPU fallback when HIP is unavailable.

## Candidate improvement to evaluate
When `require_hip_residual_engine=True` and `hip_preflight.hip_available` is false, include each `hip_preflight.runtime_blockers[]` value in top-level blockers as `hip_runtime::<value>`.

## Verification
- Focused pytest for `tests/test_mgt_residual_jacobian_consistency_probe.py`.
- Ruff/diff check for touched Python files.

## Output
Concise summary only: changed files, tests, blockers, and any concern. No full unified diff.
