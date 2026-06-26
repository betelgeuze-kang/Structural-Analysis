# Cursor worker task: Phase 5 status vocabulary contract

Goal:
Diagnose and, if straightforward, patch the Phase 5 GUI workflow so its workflow state uses the explicit status vocabulary `ready`, `blocked`, `missing`, and `error` without promoting Phase 5 readiness.

Scope:
- `src/workbench/developerPreviewWorkflow.ts`
- `src/workbench/developerPreviewWorkflowState.ts`
- `src/App.tsx`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Requirements:
- Keep the Phase 5 receipt `blocked` until execution receipts and human UX observation pass.
- Add or verify a source-level contract that all four allowed status labels are modeled.
- Do not broaden unrelated App.tsx status wording outside the Phase 5 workflow surface.
- Keep claim boundaries clear: vocabulary presence is a UI/productization contract, not execution or RC readiness.

Verification:
- Focused pytest for `tests/test_build_phase5_gui_workflow_readiness_receipt.py`.
- `npm run build`.
- Playwright list check is enough if browser execution is unavailable.

Output:
- Changed files, if any.
- Focused test results.
- Concise summary and blockers.
