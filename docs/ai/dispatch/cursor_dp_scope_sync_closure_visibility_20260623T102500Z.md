# Cursor worker slice: DP scope sync closure visibility verification

Goal:
- Make `developer_preview_readiness.scope_boundary_sync.gui` verify that the GUI consumes the generated `gap_ledger_closure_requirement_visibility` surface.

Scope:
- Inspect/edit:
  - `scripts/build_developer_preview_readiness.py`
  - `tests/test_build_developer_preview_readiness.py`
  - maybe `src/App.tsx` only to confirm existing anchors
- Preferred behavior:
  - Add explicit GUI contract booleans for closure visibility consumption and display labels.
  - Keep `scope_boundary_sync.contract_pass` true only when the closure visibility anchors are present.
  - Do not change Developer Preview blocker counts or status semantics.

Verification criteria:
- `python3 -m pytest -q tests/test_build_developer_preview_readiness.py`
- `python3 scripts/build_developer_preview_readiness.py --check` after regeneration
- `git diff --check`

Worker output:
- Return only changed files, core diff summary, tests run, failed tests, and blockers.
