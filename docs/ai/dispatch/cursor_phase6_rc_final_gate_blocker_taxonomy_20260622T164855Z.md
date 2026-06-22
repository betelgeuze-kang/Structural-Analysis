# Cursor worker task: Phase 6 RC final-gate blocker taxonomy audit

Goal: Audit the Developer Preview RC final-gate blockers for claim-boundary accuracy.

Scope:
- Focus only on RC final gates around Linux/Windows parity and clean checkout/git-clean-clone reproduction.
- Do not promote any blocked gate.
- Keep git clean clone dirty/tracked blockers visible, but do not mix them into Linux/Windows parity if they belong to the clean-checkout gate.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`

Verification criteria:
- `linux_windows_reproducibility_confirmed` remains blocked for missing parity receipts only.
- `benchmark_results_clean_checkout_regenerated` remains blocked and exposes git-clean-clone blockers precisely.
- RC pass counts do not increase.
- Claim boundary still says full Phase 3 corpus and RC are not closed.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
