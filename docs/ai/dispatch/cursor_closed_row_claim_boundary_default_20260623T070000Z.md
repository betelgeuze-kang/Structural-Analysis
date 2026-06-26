# Cursor worker slice: closed-row claim boundary default

Goal:
Review or implement a conservative default claim boundary for closed rows in `commercial_gap_ledger_status`.

Scope:
- Candidate file: `implementation/phase1/commercial_gap_ledger_status.py`
- Candidate tests: `tests/test_commercial_gap_ledger_status.py`, `tests/test_build_gap_ledger_evidence_audit.py`
- Closed G/AI-G rows currently have evidence but blank `claim_boundary`; non-closed rows already expose boundaries.
- Prefer a centralized default in the row helper over editing every row manually.

Verification criteria:
- Closed rows receive a non-empty row-level claim boundary.
- The boundary must not imply full commercial closure, external approval, or closure beyond the row's evidence.
- Existing explicit claim boundaries for partial/external rows are preserved.
- Gap ledger audit should report no closed rows missing claim boundaries.
- Focused checks if possible:
  - `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py tests/test_build_gap_ledger_evidence_audit.py`

Worker output:
- Changed files only.
- Tests/checks run and results.
- Any unsupported closure wording found.
- Blockers only if unsafe to accept.
