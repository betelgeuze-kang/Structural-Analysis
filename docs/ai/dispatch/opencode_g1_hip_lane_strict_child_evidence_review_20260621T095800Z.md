# OpenCode slice: G1 HIP lane strict child evidence review

Goal: review the current uncommitted G1 HIP lane diff and keep the lane from promoting full G1 readiness unless HIP-required child residual refresh evidence is explicit, fresh, and complete.

Scope:
- Inspect only:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`
- Treat existing uncommitted changes as untrusted and do not preserve them if they weaken the claim boundary.
- Do not edit release evidence, docs, ledgers, generated open_data artifacts, or readiness JSON.
- Do not relax thresholds, do not remove blockers, and do not promote G1 closure.

Candidate work:
- Determine whether missing or unpromoted `matrix_free_global_krylov` / `current_tangent_residual_row_correction` child evidence can still produce a ready lane.
- If a narrow strict fix is obvious, implement it with focused tests.
- If not, report the exact blocker names and next smallest patch.

Verification:
- Run focused pytest for `tests/test_run_g1_full_load_hip_newton_lane.py` only if files are changed.
- Output only changed files, test result, and blocker/next slice.
