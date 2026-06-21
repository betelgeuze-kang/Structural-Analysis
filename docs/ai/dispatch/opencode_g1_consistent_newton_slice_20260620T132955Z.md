# Goal

Identify the smallest credible local implementation slice that moves G1 toward representative full-mesh full-load residual/increment/material Newton strict PASS with fallback 0.

# Scope

- Do not modify files.
- Do not touch or revert the current PM canonical evidence sync diff.
- Inspect current G1 ledger/evidence/code only enough to find a concrete implementation target.
- Prefer implementation paths that improve the physical residual/Jacobian/Newton machinery, not status JSON or claim wording.

# Candidate files

- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_equilibrium_newton_focused_probe.py`
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_equilibrium_newton_setup.py`
- `implementation/phase1/mgt_shell_material_tangent.py`
- `implementation/phase1/mgt_cached_residual_jvp.py`
- `scripts/run_mgt_direct_residual_newton_probe.py`
- `scripts/run_mgt_equilibrium_newton_focused_probe.py`
- `scripts/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `tests/test_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_equilibrium_newton_focused_probe.py`
- `tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `tests/test_mgt_shell_material_nonlinear_tangent.py`

# Verification criteria for your summary

Return only the standard worker summary sections. Include:

- The exact files inspected.
- The current authoritative G1 blockers and the evidence artifact names that prove them.
- One recommended implementation slice with candidate file(s), expected behavior change, and focused tests/gates to run.
- Any blocker that makes implementation infeasible without external state or long heavy runs.
