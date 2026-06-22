# Cursor worker slice: gap ledger evidence audit

Goal:
Add or audit a conservative receipt that verifies the commercial/AI gap ledger rows are not overstating closure.

Scope:
- Read `commercial_gap_ledger_status.json`.
- Closed rows must have non-empty evidence and no blockers.
- Non-closed rows must keep blockers and claim boundaries visible.
- The audit must not close any G1-G10 or AI-G1-AI-G10 row by itself.
- The audit should expose advisory data for closed rows missing explicit row-level claim boundaries, without necessarily failing if the row has a next gate.

Candidate files:
- `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
- New candidate: `scripts/build_gap_ledger_evidence_audit.py`
- New candidate: `tests/test_build_gap_ledger_evidence_audit.py`
- Optional integration: `scripts/report_gap_closure_status.py`

Verification criteria:
- Receipt shows total rows, closed rows, non-closed rows, closed evidence coverage, and non-closed blocker/claim-boundary coverage.
- `contract_pass` means the ledger representation is evidence-auditable, not that full commercial closure is achieved.
- Claim boundary says it does not create evidence, external receipts, closure, or readiness.
- Focused checks if possible:
  - `python3 -m pytest -q tests/test_build_gap_ledger_evidence_audit.py`
  - `python3 scripts/build_gap_ledger_evidence_audit.py --check`

Worker output:
- Changed files only.
- Tests/checks run and results.
- Any unsupported closure claim found.
- Blockers only if this slice cannot be safely accepted.
