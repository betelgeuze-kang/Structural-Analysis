# OpenCode slice: G1 row-correction nonterminal HIP residual refresh split

Goal:
- In `run_mgt_direct_residual_newton_probe.py`, avoid overwriting accepted HIP row-correction residuals with CPU full-assembly residuals during nonterminal multi-pass row-correction promotions.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus on the row-correction promotion block after `accepted_trial = trial_rows[best_gate_trial_index]`.

Implementation intent:
- For HIP-required accepted row candidates, preserve `current_residual/current_rhs/current_free` from the accepted candidate HIP batch result.
- If another row pass needs a tangent refresh, CPU full assembly may still be used for `current_stiffness`, but receipt metadata must classify this as CPU tangent refresh only, not CPU residual acceptance refresh.
- Keep fallback-zero blocked when CPU tangent refresh remains.

Verification criteria:
- Focused tests show nonterminal HIP row promotion has no `row_correction_cpu_residual_acceptance_refresh_used` boundary, but still has `row_correction_cpu_tangent_refresh_used`.
- Do not close G1 or hide any CPU tangent fallback.
