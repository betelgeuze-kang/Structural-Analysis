# OpenCode slice: EB reused-evidence snapshot review

Goal: review the current diff for one narrow release-readiness invariant:
`external_benchmark_submission_updates.reused_evidence=true` must never allow `product_readiness_snapshot.json` to mark external benchmark receipts ready, even if the sidecar has receipt-looking fields.

Scope:
- `scripts/build_product_readiness_snapshot.py`
- `tests/test_build_product_readiness_snapshot.py`
- Current generated `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`

Do not edit files.
Do not inspect raw customer data, `.env*`, credentials, or external services.
Do not suggest synthesizing EB receipts.

Output limit: 20 lines max.
Report only:
- PASS/FAIL for the invariant.
- Missing test names if any.
- Any blocker or concrete patch suggestion.
