# Cursor worker task: Phase 6 UX observation handoff surface audit

Goal: Audit whether Developer Preview RC status exposes the human new-user UX observation handoff evidence without promoting the gate.

Scope:
- Do not create or fake human observation evidence.
- Do not mark `new_user_core_workflow_observation_passed` ready.
- Inspect the UX observation report, intake packet, RC status builder, and tests.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `scripts/build_ux_new_user_observation_report.py`
- `scripts/build_ux_new_user_observation_intake_packet.py`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Verification criteria:
- UX final gate remains blocked until a real human new-user observation report passes.
- RC status references both the report and intake packet as evidence/handoff.
- Known limitations expose owner action and validation commands from the UX report/intake packet.
- RC pass counts do not increase.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
