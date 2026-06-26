# Cursor worker task: Phase 6 UX observation contract

Goal:
Strengthen the Developer Preview RC `new_user_core_workflow_observation_passed` evidence contract without closing the gate or inventing human observation evidence.

Scope:
- `scripts/build_ux_new_user_observation_report.py`
- `scripts/build_ux_new_user_observation_intake_packet.py`
- `scripts/build_developer_preview_rc_status.py`
- `docs/templates/ux_new_user_observation.template.json`
- `tests/test_build_ux_new_user_observation_report.py`
- `tests/test_build_ux_new_user_observation_intake_packet.py`
- `tests/test_build_developer_preview_rc_status.py`

Requested implementation:
- Add an explicit five-step observed workflow contract for:
  - Import
  - Model Health
  - Analysis Setup
  - Run & Monitor
  - Compare & Report
- Require human observation evidence to include all five steps with per-step outcome/pass signals.
- Keep missing/template evidence blocked. Do not claim the UX final gate ready without a passing human record.
- Surface required workflow steps, missing steps, observed/pass counts, and workflow blockers in the report, intake packet, and RC known-limitations handoff.
- Preserve the claim boundary that automated/browser rehearsal and intake packets cannot close the RC UX gate by themselves.

Verification criteria:
- Focused tests pass for the three test files listed above.
- Generated UX report/intake remain blocked with the current missing observation source.
- `developer_preview_rc_status.json` remains blocked and the UX final gate remains blocked.
- Report concise changed files, tests run, blockers, and any unimplemented suggestions only.
