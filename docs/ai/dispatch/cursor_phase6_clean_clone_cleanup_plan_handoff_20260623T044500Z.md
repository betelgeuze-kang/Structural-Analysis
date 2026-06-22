# Cursor worker slice: Phase 6 clean-clone cleanup plan handoff

Goal:
Wire the existing Phase 3 release-control cleanup plan into the Developer Preview RC status handoff so the `benchmark_results_clean_checkout_regenerated` blocker distinguishes local clean-checkout pass from git-clean-clone blocked-by-untracked/dirty inputs.

Scope:
- Inspect only Developer Preview RC status builder/tests and the existing Phase 3 cleanup-plan receipt.
- Candidate files:
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - `implementation/phase1/release_evidence/productization/phase3_release_control_cleanup_plan.json`

Requirements:
- Preserve RC `blocked` status and final gate counts unless current evidence truly changes.
- Do not commit, push, run git add, or mutate remote state.
- Include cleanup plan path/status, candidate commit set count, recommended action counts, human handoff next action, and verification commands in RC known limitations.
- Claim boundary must say this is a human handoff and does not prove clean clone reproduction.

Verification criteria:
- Focused RC status tests pass.
- RC status `--check` remains meaningful after regeneration.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
