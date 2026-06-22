# Cursor worker slice: Phase 6 benchmark scale status receipt

Goal:
Create a conservative Phase 6 benchmark-scale status receipt that aggregates the medium-model and large-model Phase 3 readiness receipts for the Developer Preview RC final gates.

Scope:
- Candidate files:
  - new script/test for Phase 6 benchmark scale status
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - existing medium/large Phase 3 readiness receipts as read-only references

Requirements:
- The receipt must remain blocked while medium scorecards are `0/5` and large crash/OOM-free executions are `0/2`.
- Preserve separate medium and large blocker lists and claim boundaries.
- Do not count parser-only topology evidence as medium pass evidence.
- Do not count policy-only acquisition rows as large execution evidence.
- Do not claim RC readiness, Phase 3 closure, or source acquisition.

Verification criteria:
- Focused tests pass.
- RC status consumes the new receipt and remains blocked.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
