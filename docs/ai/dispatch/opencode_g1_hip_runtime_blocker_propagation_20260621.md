# OpenCode Slice: G1 HIP Runtime Blocker Propagation

Goal: Inspect and, if straightforward, implement propagation of ROCm/HIP runtime blockers from the HIP-required residual/Jacobian consistency receipt into the G1 full-load HIP Newton lane report.

Scope:
- Candidate code: `scripts/run_g1_full_load_hip_newton_lane.py`
- Candidate tests: `tests/test_run_g1_full_load_hip_newton_lane.py`
- Evidence source: `implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json`

Required behavior:
- Read `rocm_hip_runtime_preflight.runtime_blockers` from the HIP consistency proof receipt.
- Preserve the runtime blockers in `hip_consistency_proof` summary.
- Add explicit lane blockers for each runtime blocker, without promoting any readiness state.
- Keep existing generic blockers such as `hip_consistency_proof_gate_not_passed` and `hip_consistency_proof_has_blockers`.

Verification:
- Focused pytest for `tests/test_run_g1_full_load_hip_newton_lane.py`.
- Ruff on touched Python files.
- No readiness promotion, no synthetic evidence, no receipt claim closure.

Output summary only:
- Changed files.
- Tests run and result.
- Any blockers.
