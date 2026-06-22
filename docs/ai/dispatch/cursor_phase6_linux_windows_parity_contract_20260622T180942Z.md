# Cursor Worker Slice: Phase 6 Linux/Windows Parity Contract Audit

Goal:
Audit the Developer Preview RC Linux/Windows reproducibility handoff so it is actionable without claiming parity.

Scope:
- Inspect only:
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json`
  - `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`
- Do not edit protected evidence receipts directly.
- Do not claim Linux/Windows parity or RC closure.

Report:
- Missing fields that would make future Linux/Windows platform receipts verifiable.
- Exact test assertions for required platform receipt schema, stable checksum comparisons, and clean-clone blocker separation.
- Claim-boundary risks if local clean checkout replay is mistaken for cross-platform parity.

Verification criteria:
- Required platforms remain `linux` and `windows`.
- Current platform receipts remain empty until real platform runs are attached.
- Platform receipt template must require OS identity, source commit, command results, stable artifact checksums, expected scorecard identity, and no local dirty inputs.
- The RC gate must remain blocked with `linux_windows_parity_receipts_missing`.
