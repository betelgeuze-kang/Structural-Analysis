# Cursor worker slice: Developer Preview GUI closure visibility

Goal:
- Make the GUI Developer Preview readiness snapshot consume and display the existing `gap_ledger_closure_requirement_visibility` summary from `developer_preview_readiness.json`.

Scope:
- Inspect/edit:
  - `src/App.tsx`
  - frontend/static contract tests that inspect `src/App.tsx`, likely `tests/test_frontend_entry_shell.py`
- Preferred behavior:
  - Add compact metrics/notes for closure requirements, e.g. pass/total and failed count.
  - Include claim-safe wording that this is visibility only and does not close G1/G6/G7 or promote commercial readiness.
  - Do not alter readiness status, blocker count, or existing scope/future-commercial wording.

Verification criteria:
- Focused tests pass for the touched frontend contract surface.
- `npm run build` should still pass if feasible.
- `git diff --check` passes.

Worker output:
- Return only changed files, core diff summary, tests run, failed tests, and blockers.
