Goal: Audit the readiness failure-fix slice for honest claim boundaries.

Scope:
- `scripts/build_template_evidence_safety_report.py`
- `docs/templates/customer_shadow_evidence.template.json`
- `docs/templates/fresh_validation_receipt.template.json`
- `tests/test_build_template_evidence_safety_report.py`
- `tests/test_commercial_gap_ledger_status.py`
- `tests/test_pm_canonical_release_area_sync.py`
- `implementation/phase1/release_evidence/productization/template_evidence_safety_report.*`
- `implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.*`
- `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.*`

Check:
- Customer shadow and fresh validation templates must not contain affirmative pass signals or be accepted as release evidence.
- G1 residual/Jacobian expectations must stay partial and must not imply full nonlinear solver closure.
- PM release-area blockers in completion audit must match `pm_release_gate_report.json.release_area_blockers`.
- Product and Developer Preview readiness artifacts must remain blocked/stale when blockers are still present.

Please return only:
- changed files, if any
- test commands/results, if run
- core findings
- blockers
