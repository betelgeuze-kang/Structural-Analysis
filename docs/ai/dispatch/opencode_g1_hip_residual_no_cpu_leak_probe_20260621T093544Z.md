# OpenCode slice: G1 HIP residual no-CPU-leak probe

Goal: find the smallest implementable G1/HIP readiness improvement that prevents a HIP-required residual/Newton lane from relying on CPU residual acceptance or CPU tangent refresh.

Scope:
- Inspect only:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
  - `implementation/phase1/mgt_hip_full_residual_backend.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`
  - `tests/test_mgt_direct_residual_newton_probe.py`
- Do not edit release evidence or docs.
- Do not relax thresholds or promote G1 closure.
- Do not add synthetic HIP evidence.

Candidate work:
- Identify any path where `--matrix-free-global-krylov-require-hip-batch-replay` or `--current-tangent-residual-row-require-hip-batch-replay` can still pass while CPU residual/tangent refresh is used for acceptance.
- If a narrow fix is obvious, implement it with focused tests.
- If no safe narrow fix exists, report the exact current guard coverage and the next smallest missing guard.

Verification:
- Run focused pytest for any touched tests.
- Output only changed files, test result, and blocker/next slice.
