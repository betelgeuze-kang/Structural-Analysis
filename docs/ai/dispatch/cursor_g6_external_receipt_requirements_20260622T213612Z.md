# Goal
Strengthen G6 external V&V evidence boundaries so local dry-run packages, signed templates, or metadata refreshes cannot be mistaken for external benchmark/residual holdout closure.

# Scope
- Inspect/update only if useful:
  - `implementation/phase1/commercial_gap_ledger_status.py`
  - `tests/test_commercial_gap_ledger_status.py`
  - generated `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
  - downstream audit/snapshot artifacts if regenerated
- Preserve G6 as `external_blocked` unless current authoritative evidence proves EB receipts 4/4 and strict RH closure 3/3.
- Add machine-readable external receipt/closure requirements if missing:
  - four named EB receipt lanes must be attached
  - strict RH closure count must meet target
  - metadata-only refresh and local signed templates must remain non-closing evidence

# Verification Criteria
- G6 remains `external_blocked` and `locally_closable=false`.
- Tests assert the external closure requirements/gap summary and claim boundary.
- Focused verification passes:
  - `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py`
  - `python3 scripts/report_commercial_gap_ledger_status.py --output-json /tmp/commercial_gap_ledger_status.json`

# Output
Return only changed files, core diff summary, test commands/results, and blockers.
