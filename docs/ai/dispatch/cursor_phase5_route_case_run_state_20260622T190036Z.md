# Cursor Worker Task: Phase 5 Route/Case/Run State

Goal:
Move the Phase 5 GUI shell toward the required route/case/run-centered state model without broad refactoring.

Scope:
- Do not replace the full `ResourceMap`.
- Add a small typed route/case/run workflow state model under `src/workbench/`.
- Render route/case/run identifiers in the Developer Preview workflow shell.
- Update the Phase 5 readiness receipt so it detects this state model and keeps readiness blocked until execution and human UX evidence exist.
- Keep claim boundaries conservative.

Candidate files:
- `src/workbench/developerPreviewWorkflow.ts`
- new `src/workbench/developerPreviewWorkflowState.ts`
- `src/App.tsx`
- `src/index.css`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Verification criteria:
- `npm run build`
- focused Phase 5 pytest passes
- Playwright test discovery lists the workflow smoke
- Phase 5 receipt remains `blocked`
- route/case/run state is reported separately from execution pass and human UX observation.
