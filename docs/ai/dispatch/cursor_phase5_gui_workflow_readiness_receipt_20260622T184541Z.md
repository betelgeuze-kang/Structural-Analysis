# Cursor Worker Task: Phase 5 GUI Workflow Readiness Receipt

Goal:
Add an evidence-only Phase 5 GUI workflow readiness receipt for the required Developer Preview GUI workflow:
Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report.

Scope:
- Keep claims conservative. Do not mark Phase 5, UX, or Developer Preview RC ready.
- The receipt should inspect local source/evidence surfaces and report ready/blocked per workflow step.
- It should distinguish actual GUI surface coverage from observation-template/handoff coverage.
- Do not refactor `src/App.tsx`.

Candidate files:
- `src/App.tsx`
- `scripts/build_ux_new_user_observation_report.py`
- `scripts/build_ux_new_user_observation_intake_packet.py`
- `scripts/build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- new `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- new `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- new `implementation/phase1/release_evidence/productization/phase5_gui_workflow_readiness_receipt.json`

Verification criteria:
- Receipt status remains `blocked` unless all five exact GUI workflow steps are proven on the actual GUI surface.
- It records all five required steps and missing/partial GUI coverage.
- It includes a claim boundary that observation templates/handoff packets do not prove GUI implementation or human UX pass.
- Run the new focused pytest.
- Run ruff on the new script/test.
- Regenerate the new receipt.
