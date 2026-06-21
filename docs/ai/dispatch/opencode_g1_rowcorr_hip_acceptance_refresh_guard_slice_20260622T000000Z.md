# OpenCode slice: G1 row-correction HIP acceptance refresh guard

Goal:
- Inspect row-correction promotion in `run_mgt_direct_residual_newton_probe.py`.
- Verify whether HIP-required row-correction promotions still refresh accepted residual/tangent through CPU `assemble_residual`.
- Add the narrowest guard/receipt metadata so fallback-zero audit cannot pass a HIP-required promoted row-correction path that used CPU residual/tangent acceptance refresh.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus around `_g1_fallback_zero_audit` and the row-correction promotion block after `current_u = trial_vectors[best_gate_trial_index]`.

Verification criteria:
- Add focused test coverage for row-correction CPU residual/tangent acceptance refresh under `require_hip_batch_replay=True`.
- Do not close G1 or relax claim boundaries.
- Summarize only changed files, tests, failed tests, and blockers.
