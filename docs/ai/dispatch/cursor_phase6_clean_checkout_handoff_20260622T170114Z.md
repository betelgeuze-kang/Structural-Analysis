# Cursor worker task: Phase 6 clean-checkout reproduction handoff audit

Goal: Audit the Developer Preview RC final-gate handoff for `benchmark_results_clean_checkout_regenerated`.

Scope:
- Do not commit, stage, or mutate git state.
- Do not promote `benchmark_results_clean_checkout_regenerated`.
- Inspect RC status builder/tests and Phase 3 clean checkout / git clean clone receipts.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_clean_checkout_reproduction.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json`

Verification criteria:
- Local isolated clean checkout replay pass remains visible.
- Git clean-clone replay remains blocked with tracked/untracked/dirty input blockers.
- RC status exposes required inputs, blocker taxonomy, owner action, and claim boundary.
- RC pass counts do not increase.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
