# Cursor worker slice: DP/RC markdown closure visibility

Goal:
- Ensure the human-readable Developer Preview and Developer Preview RC markdown reports expose the existing gap-ledger closure requirement visibility summary.

Scope:
- Inspect and edit only if needed:
  - `scripts/build_developer_preview_readiness.py`
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_readiness.py`
  - `tests/test_build_developer_preview_rc_status.py`
- Preferred behavior:
  - Add a compact markdown section showing closure requirement pass/fail counts and failed requirement IDs (or a bounded list plus count).
  - Source data must come from existing `gap_ledger_closure_requirement_visibility`.
  - Do not alter blocker counts, statuses, final gate counts, or readiness claims.
  - Preserve claim boundary wording that this does not close G1/G6/G7 or promote commercial readiness.

Verification criteria:
- Focused tests pass:
  - `python3 -m pytest -q tests/test_build_developer_preview_readiness.py tests/test_build_developer_preview_rc_status.py`
- `--check` commands for DP readiness and DP RC status pass after regeneration.

Worker output:
- Return only changed files, core diff summary, tests run, failed tests, and blockers.
