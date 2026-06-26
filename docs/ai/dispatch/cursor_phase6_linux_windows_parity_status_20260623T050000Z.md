# Cursor worker slice: Phase 6 Linux/Windows parity status receipt

Goal:
Create a conservative Phase 6 Linux/Windows parity status receipt that formalizes the current RC handoff template into an auditable artifact, without claiming parity or Developer Preview RC readiness.

Scope:
- Inspect only Developer Preview RC status builder/tests and Phase 3 reproducibility receipts.
- Candidate files:
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - new narrowly scoped script/test for Phase 6 parity status
  - `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Requirements:
- The new receipt should be blocked when Linux/Windows platform replay receipts are missing.
- It should define required platforms, expected scorecard/checksums, receipt schema/template, comparison contract, blocked_by, owner_action, and claim_boundary.
- It must not treat local git clean-clone status as Linux/Windows parity.
- RC final gate should consume the parity status receipt rather than only an inline handoff.
- Do not commit, push, mutate remote state, or run destructive cleanup.

Verification criteria:
- Focused tests pass.
- RC status check remains consistent after regeneration.
- Claim boundary preserves blocked status and no readiness promotion.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
