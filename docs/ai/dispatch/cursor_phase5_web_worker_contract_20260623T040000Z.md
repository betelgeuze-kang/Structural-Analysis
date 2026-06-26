# Cursor worker slice: Phase 5 Web Worker boundary contract

Goal:
Add a conservative Phase 5 contract showing that large IFC parsing and result processing are routed to a Web Worker boundary, without promoting Phase 5 or Developer Preview RC readiness.

Scope:
- Inspect only the Phase 5 workflow surface and receipt builder.
- Candidate files:
  - `src/workbench/developerPreviewWorkflow.ts`
  - `src/workbench/DeveloperPreviewWorkflowPanel.tsx`
  - `src/index.css`
  - `scripts/build_phase5_gui_workflow_readiness_receipt.py`
  - `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
  - `tests/frontend/developer-preview-workflow.spec.ts`
- If useful, add a narrowly scoped worker file under `src/workbench/`.

Requirements:
- Preserve the current blocked status and all existing blockers for missing execution receipts, browser execution receipt, and human observation.
- Add explicit anchors for Web Worker boundary, IFC parse, result processing, and a claim boundary that this is not execution evidence.
- Keep the receipt claim boundary conservative: structure/contract only, not proof of actual task execution.
- Do not touch ledgers, unrelated receipts, commit, push, or destructive commands.

Verification criteria:
- Focused Python receipt tests pass.
- Frontend build still passes if you change TypeScript/React.
- Receipt regeneration/check remains consistent if you update the builder.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
