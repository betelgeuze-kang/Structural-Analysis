# Goal
Propagate nonclosed gap closure-requirement pass/fail counts from `commercial_gap_ledger_status.json` into `gap_ledger_evidence_audit.json` and the product readiness snapshot summary.

# Scope
- Inspect/update:
  - `scripts/build_gap_ledger_evidence_audit.py`
  - `scripts/build_product_readiness_snapshot.py`
  - `tests/test_build_gap_ledger_evidence_audit.py`
  - `tests/test_build_product_readiness_snapshot.py`
- Preserve current gap statuses. Do not close G1, G6, or G7.
- Add machine-readable summary fields for rows that carry `evidence.closure_requirements` or `evidence.external_closure_requirements`, such as requirement count, passed count, failed count, and failed requirement IDs.
- Ensure the product snapshot audit split summary surfaces nonclosed rows with failed closure requirements.

# Verification Criteria
- G1/G6/G7 row outcomes include requirement pass/fail counts.
- The audit remains `ready` but does not claim `full_gap_ledger_ready`.
- Focused tests pass:
  - `python3 -m pytest -q tests/test_build_gap_ledger_evidence_audit.py tests/test_build_product_readiness_snapshot.py`
- Regenerated artifacts remain honest/open.

# Output
Return only changed files, core diff summary, test commands/results, and blockers.
