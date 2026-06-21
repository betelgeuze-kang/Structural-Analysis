# OpenCode slice: G1 row-correction HIP replay receipt hardening

Goal:
- Inspect `implementation/phase1/run_mgt_direct_residual_newton_probe.py` row-correction residual-only finite-difference and alpha replay paths.
- Find the narrowest implementation improvement that makes the row-correction path more explicitly ROCm/HIP-residual driven rather than CPU diagnostic when HIP replay is configured.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate tests: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus on `current_tangent_residual_row_*batch*_replay`, `row_evaluate_residual_candidates`, and trial row receipt metadata.

Verification criteria:
- If code changes are made, add/adjust focused pytest coverage showing row-correction FD/alpha candidates are replayed through HIP batch backend metadata and do not silently fall back to CPU when HIP is required.
- Preserve the G1 claim boundary: do not promote G1 to closed; local HIP runtime may be unavailable.
- Summarize only changed files, focused tests, blockers, and whether any CPU fallback remains visible in receipts.
