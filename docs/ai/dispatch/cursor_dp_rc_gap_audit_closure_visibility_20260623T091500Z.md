# Cursor worker slice: DP/RC gap audit closure visibility

Goal:
- Propagate existing `gap_ledger_evidence_audit` closure requirement failure summaries into Developer Preview and Developer Preview RC evidence surfaces without promoting readiness or duplicating blocker counts.

Scope:
- Inspect:
  - `scripts/build_developer_preview_readiness.py`
  - `scripts/build_developer_preview_rc_status.py`
  - `tests/test_build_developer_preview_readiness.py`
  - `tests/test_build_developer_preview_rc_status.py`
  - `implementation/phase1/release_evidence/productization/gap_ledger_evidence_audit.json`
- Preferred implementation:
  - Add a non-blocking visibility/known-limitation summary derived from `gap_ledger_evidence_audit.row_outcomes`.
  - Preserve current blocker counts and status outcomes unless a current test proves they are already stale.
  - Do not claim G1/G6/G7 closure.
  - Keep future commercial blockers separated from Developer Preview blockers.

Verification criteria:
- `developer_preview_readiness.blocker_count` remains current unless an existing authoritative input truly changes it.
- `developer_preview_rc_status.final_gate_count` remains 9.
- G1/G6/G7 failed closure requirement IDs are visible in a structured JSON surface.
- Focused tests pass:
  - `python3 -m pytest -q tests/test_build_developer_preview_readiness.py tests/test_build_developer_preview_rc_status.py`
  - relevant `--check` commands for regenerated artifacts.

Worker output:
- Return only changed files, core diff summary, tests run, failed tests, and blockers.
