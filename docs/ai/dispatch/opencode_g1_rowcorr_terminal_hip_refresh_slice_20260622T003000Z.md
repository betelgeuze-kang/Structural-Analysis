# OpenCode slice: G1 row-correction terminal HIP accepted residual refresh

Goal:
- Convert terminal HIP-required row-correction promotion so it can reuse the accepted candidate residual from HIP batch replay instead of always calling CPU `assemble_residual` after promotion.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus around row-correction `trial_vectors`, candidate residual evaluation, and promotion block.

Implementation intent:
- Store candidate residual/free/rhs vectors alongside `trial_vectors`.
- If a HIP-required row-correction promotion is terminal for that row-correction run, and the accepted candidate row was evaluated by HIP batch replay with stable free DOFs, set `current_residual/current_rhs/current_free` from the accepted candidate result and record `accepted_state_refresh_cpu_used=false`.
- Only use CPU full assembly refresh when another row pass needs a fresh tangent/operator.

Verification criteria:
- Add/adjust focused tests proving terminal HIP row promotion does not record CPU residual/tangent refresh blockers.
- Keep nonterminal/multipass row promotion visibly blocked if it still needs CPU tangent refresh.
- Do not close G1 or relax residual/increment/material Newton gates.
