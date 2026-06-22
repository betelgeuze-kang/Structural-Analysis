# Cursor Worker Task: Phase 5 GUI Workflow Shell

Goal:
Move Phase 5 GUI productization forward by adding a real, visible five-step Developer Preview workflow shell to the React app while keeping readiness blocked until execution/human UX evidence exists.

Scope:
- Do not refactor the whole `src/App.tsx`.
- Add a small structured workflow model under `src/workbench/` if useful.
- Render the five required steps in the app: Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report.
- Each step should show blocked/missing/check status and concise operational signals for the Phase 5 required capabilities.
- Update `scripts/build_phase5_gui_workflow_readiness_receipt.py` so it distinguishes:
  - actual GUI workflow shell coverage,
  - actual execution/task pass evidence,
  - human UX observation evidence.
- Do not promote Phase 5, human UX, or Developer Preview RC readiness.

Candidate files:
- `src/App.tsx`
- `src/index.css`
- `src/workbench/resourceModel.ts`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`

Verification criteria:
- `phase5_gui_workflow_readiness_receipt.json` remains `status=blocked`.
- GUI shell coverage should be represented separately from execution/human UX pass.
- Run focused pytest for Phase 5 and RC status.
- Run ruff on touched Python files.
- Run `npm run build` if UI files are changed.
