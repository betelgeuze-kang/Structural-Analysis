# OpenCode slice: product readiness evidence resync sweep

Goal: identify safe local regeneration commands for product-readiness evidence JSON files whose `source_commit_sha` or metadata is stale against the current HEAD.

Scope:
- Read `scripts/build_product_readiness_snapshot.py`.
- Inspect only scripts that generate these artifacts:
  - `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
  - `implementation/phase1/release_evidence/productization/gap_closure_status.json`
  - `implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json`
  - `implementation/phase1/release_evidence/productization/mgt_g1_direct_residual_terminal_gate_report.json`
  - `implementation/phase1/customer_shadow_evidence_status.json`
  - `implementation/phase1/workstation_delivery_readiness.json`
  - `implementation/phase1/release/independent_product_readiness.json`
  - `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
  - `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
  - `implementation/phase1/release_evidence/productization/license_status_closure_report.json`
  - external benchmark readiness/update JSONs if a local read-only generator exists.

Constraints:
- Do not edit files.
- Do not create or fake receipts, customer cases, UX observations, license approvals, CI streaks, or external benchmark evidence.
- Do not use credentials, push, mutate GitHub, or call remote APIs except read-only commands already used by existing scripts.

Output:
- List safe regeneration commands.
- List artifacts that should remain stale or blocked because regeneration would require external evidence.
- Mention any command that might query GitHub or need credentials.
