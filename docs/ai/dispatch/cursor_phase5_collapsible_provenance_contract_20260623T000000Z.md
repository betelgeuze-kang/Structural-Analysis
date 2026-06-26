# Cursor worker task: Phase 5 collapsible provenance contract

Goal:
Diagnose and, if straightforward, patch the Phase 5 Developer Preview workflow panel so advanced provenance is provided in a collapsed disclosure instead of as always-expanded text.

Scope:
- `src/workbench/DeveloperPreviewWorkflowPanel.tsx`
- `src/index.css`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Requirements:
- Use a native `details`/`summary` or equivalent accessible disclosure inside the Phase 5 workflow panel.
- Preserve all existing `data-phase5-*` anchors.
- Add a receipt contract proving the provenance disclosure exists.
- Keep Phase 5 and Developer Preview RC blocked until execution receipts and human UX observation pass.

Verification:
- `python3 -m pytest -q tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `npm run build`
- `npx playwright test tests/frontend/developer-preview-workflow.spec.ts --list`

Output:
- Changed files, if any.
- Focused test results.
- Concise summary and remaining blockers.
