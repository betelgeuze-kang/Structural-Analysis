# Cursor worker slice: Phase 6 UX observation status

Goal:
Add or audit a conservative Phase 6 UX observation status receipt that aggregates the human new-user observation report, the owner intake packet, and Phase 5 GUI workflow execution evidence for the Developer Preview RC final gate.

Scope:
- Keep the RC gate blocked unless a real human new-user observation passes and Phase 5 execution evidence is proven.
- Do not create or fake human observation evidence.
- Do not mark the GUI workflow, task-based browser execution, or Developer Preview RC as ready unless existing authoritative receipts prove it.

Candidate files:
- `scripts/build_ux_new_user_observation_report.py`
- `scripts/build_ux_new_user_observation_intake_packet.py`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- New candidate: `scripts/build_phase6_ux_observation_status.py`
- New candidate: `tests/test_build_phase6_ux_observation_status.py`
- Receipts under `implementation/phase1/release_evidence/productization/`

Verification criteria:
- The new status receipt, if added, has explicit blockers for missing human observation and unproven workflow/browser execution.
- The RC final gate `new_user_core_workflow_observation_passed` cites the new Phase 6 UX status receipt.
- Claim boundary says automated browser/task tests and intake packets do not replace human observation.
- Run focused tests/checks if possible:
  - `python3 -m pytest -q tests/test_build_phase6_ux_observation_status.py tests/test_build_developer_preview_rc_status.py`
  - `python3 scripts/build_phase6_ux_observation_status.py --check`
  - `python3 scripts/build_developer_preview_rc_status.py --check`

Worker output:
- Changed files only.
- Tests/checks run and results.
- Any unsupported closure claim found.
- Any blocker that prevents safe acceptance.
