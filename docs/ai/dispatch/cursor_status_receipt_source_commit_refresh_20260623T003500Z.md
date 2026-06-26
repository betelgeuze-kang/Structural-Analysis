# Cursor worker slice: status receipt source-commit refresh

Goal:
- Refresh locally regeneratable status receipts that currently trigger `stale_or_inconsistent:source_commit_mismatch:*` blockers in readiness snapshots.

Scope:
- Candidate receipts/builders:
  - `implementation/phase1/customer_shadow_evidence_status.json`
  - `implementation/phase1/release/external_benchmark_submission_readiness.json`
  - `implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json`
  - `implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json`
  - `implementation/phase1/release_evidence/productization/gap_closure_status.json`
  - `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
  - `implementation/phase1/release/independent_product_readiness.json`
  - `implementation/phase1/release_evidence/productization/license_status_closure_report.json`
  - `implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.json`
  - `implementation/phase1/release_evidence/productization/mgt_g1_direct_residual_terminal_gate_report.json`
- Likely commands/scripts:
  - `scripts/check_customer_shadow_evidence_status.py`
  - `implementation/phase1/generate_external_benchmark_submission_readiness.py`
  - `implementation/phase1/preview_external_benchmark_submission_after_review_updates.py`
  - `scripts/build_fresh_full_validation_lane_status.py`
  - `scripts/report_gap_closure_status.py`
  - `scripts/build_github_actions_ci_streak_evidence.py`
  - `scripts/check_independent_product_readiness.py`
  - `scripts/build_license_status_closure_report.py`
  - `scripts/build_paid_pilot_scope_guard_report.py`
  - `scripts/build_mgt_g1_direct_residual_terminal_gate_report.py`

Constraints:
- Do not fabricate external receipts, customer shadow evidence, GitHub CI success, license approval, or paid pilot approval.
- Preserve blocked/incomplete statuses and blockers.
- Only remove stale source-commit mismatch when the receipt is genuinely regenerated at current HEAD.
- Do not use network-dependent commands unless they degrade to explicit blocked/query-failed evidence.

Verification:
- Show which receipts were refreshed and which still cannot be refreshed.
- Run focused tests/checks for changed builders if available.
- Rebuild `product_readiness_snapshot` and `developer_preview_readiness`, then confirm source-commit mismatch blockers are reduced without promoting readiness.
