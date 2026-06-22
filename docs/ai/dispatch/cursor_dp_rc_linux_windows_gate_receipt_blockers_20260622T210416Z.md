# Cursor Worker Slice: DP RC Linux/Windows Gate Receipt Blockers

Goal:
Make the Developer Preview RC `linux_windows_reproducibility_confirmed` final gate consume blocker detail from `phase6_linux_windows_parity_status.json` instead of relying on a single hard-coded blocker.

Scope:
- Inspect `scripts/build_developer_preview_rc_status.py`.
- Candidate tests: `tests/test_build_developer_preview_rc_status.py`.
- Do not modify platform receipts or fabricate Linux/Windows parity evidence.

Expected behavior:
- The RC final gate remains blocked.
- Its blockers should be derived from the parity status receipt, while keeping git clean-clone blockers scoped to the separate `benchmark_results_clean_checkout_regenerated` gate.
- Missing platform receipts (`linux`, `windows`) should remain visible.
- Do not promote Developer Preview RC readiness.
- Do not commit or push.

Verification criteria:
- Add/update focused tests for receipt-derived Linux/Windows gate blockers.
- Run focused pytest for `tests/test_build_developer_preview_rc_status.py` if feasible.
- Summarize changed files, tests, and blockers only.
