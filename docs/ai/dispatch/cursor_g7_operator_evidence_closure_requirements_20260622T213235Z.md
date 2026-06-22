# Goal
Strengthen G7 commercial gap status evidence so proxy/benchmark-bridge/local metadata cannot be mistaken for operator-attached real-project corpus closure.

# Scope
- Inspect/update only if useful:
  - `implementation/phase1/commercial_gap_ledger_status.py`
  - `tests/test_commercial_gap_ledger_status.py`
  - generated `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
  - downstream audit/snapshot artifacts if regenerated
- Preserve G7 as non-closed unless current authoritative evidence actually proves closure.
- Add machine-readable closure requirements/gap summary for G7 if missing, especially:
  - repo benchmark bridge count must be zero
  - metadata-only count must be zero
  - operator-attached real MGT header-ok count must meet target
  - operator real artifacts must have source mapping and rights/permission boundary where needed

# Verification Criteria
- G7 remains `partial` and its blockers remain visible.
- Tests assert closure requirements/gap summary so future regressions cannot promote bridge/proxy evidence.
- Focused verification passes:
  - `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py`
  - `python3 scripts/report_commercial_gap_ledger_status.py --output-json /tmp/commercial_gap_ledger_status.json`

# Output
Return only changed files, core diff summary, test commands/results, and blockers.
