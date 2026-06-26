# Goal
Add provenance metadata to `commercial_gap_ledger_status.json` so the product readiness snapshot can treat it as a first-class metadata artifact without changing readiness claims.

# Scope
- Inspect and update:
  - `implementation/phase1/commercial_gap_ledger_status.py`
  - `scripts/build_product_readiness_snapshot.py`
  - `tests/test_commercial_gap_ledger_status.py`
  - `tests/test_build_product_readiness_snapshot.py`
- Preserve current ledger statuses and blockers. Do not close any G1/AI-G row.
- Use existing `scripts/release_evidence_metadata.py` helper if appropriate.
- Keep claim boundary explicit: this status summarizes existing ledger/evidence state and does not create authoritative closure evidence.

# Verification Criteria
- `commercial_gap_ledger_status.json` payload includes `source_commit_sha`, `engine_version`, `input_checksums`, `reused_evidence`, and `reuse_policy`.
- Product readiness snapshot includes `commercial_gap_ledger_status` in metadata freshness rows.
- Focused tests pass:
  - `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py tests/test_build_product_readiness_snapshot.py`
- Regenerated artifacts remain honest/open where rows are partial/external-blocked.

# Output
Return only changed files, core diff summary, test commands/results, and blockers.
