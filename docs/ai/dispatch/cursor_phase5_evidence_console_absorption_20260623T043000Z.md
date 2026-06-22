# Cursor worker slice: Phase 5 Evidence Console absorption contract

Goal:
Add a conservative Phase 5 contract proving that the existing Evidence Console scope is absorbed into the final Compare & Report workflow step, without promoting Phase 5 or Developer Preview RC readiness.

Scope:
- Inspect only Phase 5 workflow files, the Evidence Console scope status receipt, and related focused tests.
- Candidate files:
  - `src/workbench/developerPreviewWorkflow.ts`
  - `src/workbench/DeveloperPreviewWorkflowPanel.tsx`
  - `src/index.css`
  - `scripts/build_phase5_gui_workflow_readiness_receipt.py`
  - `tests/test_build_phase5_gui_workflow_readiness_receipt.py`
  - `tests/frontend/developer-preview-workflow.spec.ts`
  - `implementation/phase1/release_evidence/productization/evidence_console_scope_status.json`

Requirements:
- Make Compare & Report visibly reference Evidence Console absorption.
- Link the contract to `evidence_console_scope_status.json`.
- Preserve the current blocked Phase 5 status and execution/human-observation blockers.
- Do not claim Evidence Console launch readiness, customer-shadow completion, browser UX success, or Phase 5 closure.
- Do not touch unrelated ledgers, unrelated receipts, commit, push, destructive cleanup, or external services.

Verification criteria:
- Focused Phase 5 receipt tests pass.
- Frontend build still passes if TypeScript/React changes.
- Receipt `--check` remains meaningful.

Report back only:
- Changed files.
- Tests run and result.
- Any blocker.
