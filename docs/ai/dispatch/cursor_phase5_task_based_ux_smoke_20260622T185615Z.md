# Cursor Worker Task: Phase 5 Task-Based UX Smoke

Goal:
Add a narrow task-based browser smoke test for the Developer Preview five-step workflow shell.

Scope:
- Do not refactor the app.
- Prefer a small Playwright spec under `tests/frontend/`.
- The test should load the main Vite app, verify the Phase 5 workflow shell exists, and verify all five steps are visible:
  Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report.
- It must also verify readiness is still blocked by execution/human UX evidence, not promoted by shell coverage.
- Add/adjust only minimal selectors if needed.

Candidate files:
- `tests/frontend/`
- `src/App.tsx`
- `src/workbench/developerPreviewWorkflow.ts`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`

Verification criteria:
- `npm run build`
- Run the new Playwright spec against a local Vite preview or dev server.
- Existing focused Phase 5 Python receipt test still passes.
- Do not change readiness to ready.
