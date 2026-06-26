# Cursor worker task: Phase 5 unified selection state contract

Goal:
Diagnose and, if straightforward, patch the Phase 5 Developer Preview workflow panel so 3D selection, table row, chart marker, and comparison row are represented as one unified selection-state surface.

Scope:
- `src/workbench/DeveloperPreviewWorkflowPanel.tsx`
- `src/workbench/developerPreviewWorkflow.ts`
- `src/index.css`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Requirements:
- Add/verify a source-level vocabulary for `3d`, `table`, `chart`, and `comparison_row` selection channels.
- Render DOM anchors inside the Phase 5 workflow panel proving those channels share one selection state.
- Add a receipt contract proving the unified selection state exists.
- Keep Phase 5 and Developer Preview RC blocked until execution receipts and human UX observation pass.

Verification:
- `python3 -m pytest -q tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `npm run build`
- `npx playwright test tests/frontend/developer-preview-workflow.spec.ts --list`

Output:
- Changed files, if any.
- Focused test results.
- Concise summary and remaining blockers.
