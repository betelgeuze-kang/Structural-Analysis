# Cursor worker task: Phase 6 Linux/Windows parity handoff audit

Goal: Audit the Developer Preview RC final-gate handoff for `linux_windows_reproducibility_confirmed`.

Scope:
- Do not fabricate Linux or Windows run receipts.
- Do not promote `linux_windows_reproducibility_confirmed`.
- Inspect RC status builder/tests and the Phase 3 seed reproducibility/clean-clone receipts.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`

Verification criteria:
- Linux/Windows parity gate remains blocked with `linux_windows_parity_receipts_missing`.
- RC status exposes required platforms, required commands, comparison requirements, and claim boundary.
- Git clean-clone blockers stay under the clean-checkout gate, not the parity gate.
- RC pass counts do not increase.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
