# Cursor worker task: Phase 5 workflow feature module extraction

Goal:
Diagnose and, if straightforward, extract the Developer Preview Phase 5 workflow panel out of `src/App.tsx` into a focused feature module without changing readiness claims.

Scope:
- `src/App.tsx`
- `src/workbench/developerPreviewWorkflow.ts`
- `src/workbench/developerPreviewWorkflowState.ts`
- new `src/workbench/DeveloperPreviewWorkflowPanel.tsx` if useful
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Requirements:
- Preserve all existing `data-phase5-*` DOM anchors.
- Keep Phase 5 receipt blocked until execution receipts and human UX observation pass.
- Add/verify a receipt contract proving the workflow panel is in a feature module instead of being only embedded in `App.tsx`.
- Do not refactor unrelated App sections.

Verification:
- `python3 -m pytest -q tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `npm run build`
- `npx playwright test tests/frontend/developer-preview-workflow.spec.ts --list`

Output:
- Changed files, if any.
- Focused test results.
- Concise summary and blockers.
