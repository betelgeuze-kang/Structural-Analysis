# OpenCode Worker Slice

Goal: Review the G1 followup391 shell-material continuation/status-chain changes for claim-boundary mistakes.

Scope: Inspect only the G1 shell-material continuation status builder, its tests, the related controller seed fallback, and the three ledger/improvement-plan doc snippets. Do not run long solver probes. Do not edit files unless you find a clear defect in this exact scope.

Candidate files:

- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- `tests/test_mgt_shell_material_rowcorr_budget_controller.py`
- `implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup391_multistep_target4_support4.json`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `docs/solver-consistent-newton-krylov-improvement-plan.md`

Verification criteria:

- Followup391 is represented only as residual-descent evidence, not G1 closure.
- Followup390 remains non-promoting launch-only evidence.
- The latest frontier is `8.345062176806358 N`, the residual gate remains `5e-4 N`, and blockers remain visible.
- Controller seed fallback handles prior controller JSON with `final_direct_residual_inf_n`.
- Tests are appropriately scoped and do not require long solver execution.

Return only:

- Changed files
- Test results
- Failed tests
- Core diff summary
- Blockers
