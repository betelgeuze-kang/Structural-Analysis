# Cursor worker task: Phase 5 value-kind contract

Goal:
Diagnose and, if straightforward, patch the Phase 5 Developer Preview workflow so exact values, derived proxies, and reference values are explicitly distinguished in the workflow model, DOM, and readiness receipt.

Scope:
- `src/workbench/developerPreviewWorkflow.ts`
- `src/App.tsx`
- `src/index.css`
- `scripts/build_phase5_gui_workflow_readiness_receipt.py`
- `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
- `tests/frontend/developer-preview-workflow.spec.ts`

Requirements:
- Add/verify a constrained vocabulary for `exact_value`, `derived_proxy`, and `reference_value`.
- Render visible/DOM anchors for the three kinds inside the Phase 5 workflow surface only.
- Add a receipt contract that proves the value-kind vocabulary is modeled and rendered.
- Do not promote Phase 5 readiness; execution and human UX observation blockers must remain visible.

Verification:
- Focused pytest for `tests/test_build_phase5_gui_workflow_readiness_receipt.py`.
- `npm run build`.
- `npx playwright test tests/frontend/developer-preview-workflow.spec.ts --list`.

Output:
- Changed files, if any.
- Focused test results.
- Concise summary and blockers.
