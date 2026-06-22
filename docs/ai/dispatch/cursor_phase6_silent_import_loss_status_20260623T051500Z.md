# Cursor worker slice: Phase 6 silent import loss status receipt

Goal:
Create a conservative Phase 6 silent-import-loss status receipt that aggregates the existing Phase 3 clean/dirty IFC acquisition, source/license, and import-health receipts for the Developer Preview RC final gate.

Scope:
- Candidate files:
  - new script/test for Phase 6 silent import loss status
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - existing Phase 3 IFC receipt JSON/scripts/tests as read-only references

Requirements:
- The new receipt must remain blocked unless selected clean/dirty IFC sources are acquired/checksummed, legal/license review is complete, import-health execution passes, and silent data-loss negative gate executes.
- Preserve RC `blocked`; do not promote the `silent_import_loss_zero` gate.
- Distinguish missing source/checksum/license/execution blockers.
- Include owner action and claim boundary saying expected contracts or source identity alone do not prove zero silent import loss.
- Do not download external files, commit, push, mutate remote state, or remove blockers without evidence.

Verification criteria:
- Focused tests pass.
- RC status consumes the new receipt and remains consistent.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
