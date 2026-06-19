# Goal
Integrate the new G1 shell-material adaptive global Krylov receipts into the authoritative G1 status/docs/tests without promoting G1 closure.

# Scope
- Treat these receipts as CPU-diagnostic partial progress only:
  - `implementation/phase1/release_evidence/productization/mgt_direct_residual_shell_material_adaptive_global_krylov_followup396_smoke.json`
  - `implementation/phase1/release_evidence/productization/mgt_direct_residual_shell_material_adaptive_global_krylov_followup397_compact_smoke.json`
- Preserve blockers: direct residual gate not closed, full mesh nonlinear equilibrium not closed, production ROCm/HIP residual backend not closed, consistent residual/Jacobian Newton not closed.
- Latest frontier should reflect followup397 if it is safe and monotonic: `6.117752205061414 N` versus gate `5.0e-4 N`.
- Keep claim boundaries explicit: `cpu_diagnostic_only`, `official_rocm_hip_closure_required`, `shell_pressure_load_path_policy=structural_components_only`, `apply_shell_material_tangent=True`.
- Do not edit unrelated files or revert existing dirty worktree changes.

# Candidate Files
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json`
- status refresh scripts that already consume the G1 status receipt.

# Verification Criteria
- Run focused tests for the edited status/docs path.
- Refresh the G1 shell-material status receipt and any dependent productization/gap/PM reports required by existing scripts.
- Confirm commercial gap ledger still reports G1 as `partial`, not closed.
- Return only changed files, test results, failed test names, core diff summary, and blockers.
