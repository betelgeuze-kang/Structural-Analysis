# ROCm/HIP preflight diagnostics slice

Goal: expand the strict G1 ROCm/HIP runtime preflight so receipts explain why HIP residual execution cannot start on this host or sandbox.

Scope:
- implementation/phase1/run_mgt_direct_residual_newton_probe.py
- tests/test_mgt_direct_residual_newton_probe.py
- generated HIP-required residual/Jacobian proof receipt after code commit

Constraints:
- Do not mark HIP available unless torch ROCm build and torch.cuda.is_available() are true.
- Do not fall back to CPU residual execution for HIP-required lanes.
- Do not inspect broad process configuration. Only record narrowly named ROCm/HIP visibility settings if needed.
- Preserve existing blocker semantics; add actionable fields such as /dev/kfd, /dev/dri, runtime_blockers, and ROCm command paths.

Deliverable:
- Exact fields/tests to add.
- Keep output concise; no file edits.
