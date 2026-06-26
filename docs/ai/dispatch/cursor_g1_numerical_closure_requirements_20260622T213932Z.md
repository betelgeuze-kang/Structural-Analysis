# Goal
Strengthen G1 full 3D FEA core status evidence so terminal/direct-residual/proxy diagnostics cannot be mistaken for full-mesh, full-load, material Newton closure.

# Scope
- Inspect/update only if useful:
  - `implementation/phase1/commercial_gap_ledger_status.py`
  - `tests/test_commercial_gap_ledger_status.py`
  - generated `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
  - downstream audit/snapshot artifacts if regenerated
- Preserve G1 as `partial` unless current authoritative evidence truly proves full-mesh/full-load/material Newton closure.
- Add machine-readable closure requirements/gap summary if missing:
  - full load scale 1.0 reached
  - full line/frame/surface/coupled nonlinear equilibrium closed
  - physical direct residual and increment gates pass without fallback
  - material Newton breadth/state-updated path closed
  - fallback/regularization states remain visible and non-closing

# Verification Criteria
- G1 remains `partial`.
- Tests assert closure requirements/gap summary and existing blockers stay visible.
- Focused verification passes:
  - `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py`
  - `python3 scripts/report_commercial_gap_ledger_status.py --output-json /tmp/commercial_gap_ledger_status.json`

# Output
Return only changed files, core diff summary, test commands/results, and blockers.
