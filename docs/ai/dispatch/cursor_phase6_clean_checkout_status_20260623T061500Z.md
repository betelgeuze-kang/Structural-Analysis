# Cursor worker slice: Phase 6 clean checkout reproduction status

Goal:
Add or audit a conservative Phase 6 clean-checkout reproduction status receipt for the Developer Preview RC final gate `benchmark_results_clean_checkout_regenerated`.

Scope:
- Aggregate the local clean-checkout replay receipt, the real git clean-clone replay receipt, and the Phase 3 release-control cleanup plan.
- Keep the gate blocked when the git clean-clone replay is blocked by untracked or dirty required inputs.
- Do not run `git add`, commit, push, checkout, reset, or destructive cleanup.
- Do not promote Developer Preview RC readiness.

Candidate files:
- `scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py`
- `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- `scripts/build_phase3_release_control_cleanup_plan.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- New candidate: `scripts/build_phase6_clean_checkout_status.py`
- New candidate: `tests/test_build_phase6_clean_checkout_status.py`
- Receipts under `implementation/phase1/release_evidence/productization/`

Verification criteria:
- The status receipt records local clean checkout pass separately from git clean-clone blocked state.
- It exposes human git action required, candidate release-control commit set count, blocker counts, and next verification commands.
- Its claim boundary says it does not commit, push, clean the worktree, prove Linux/Windows parity, or close full Phase 3.
- The RC final gate cites this Phase 6 status receipt.
- Focused checks if possible:
  - `python3 -m pytest -q tests/test_build_phase6_clean_checkout_status.py tests/test_build_developer_preview_rc_status.py`
  - `python3 scripts/build_phase6_clean_checkout_status.py --check`
  - `python3 scripts/build_developer_preview_rc_status.py --check`

Worker output:
- Changed files only.
- Tests/checks run and results.
- Any unsupported closure claim found.
- Blockers only if the slice cannot be safely accepted.
