# Cursor worker slice: release freshness stale artifacts

Goal:
- Refresh locally regeneratable productization artifacts whose top-level `source_commit_sha` does not match current HEAD.

Scope:
- Candidate stale artifacts:
  - `customer_shadow_evidence_intake_packet.json`
  - `evidence_console_scope_status.json`
  - `github_actions_self_hosted_runner_status.json`
  - `mgt_g1_followup387_shell_material_budgeted_continuation_status.json`
  - `mgt_residual_jacobian_consistency_probe.json`
  - `p0_closure_status.json`
  - `p1_readiness_status.json`
  - `p1_benchmark_breadth_status.json`
  - `release_evidence_freshness_report.json`
  - `residual_level3_status.json`

Constraints:
- Do not fabricate customer shadow evidence, GitHub runner availability, external validation, or full G1 closure.
- Do not run long G1 continuation probes.
- Prefer metadata/status builders and `--check`/read-only modes where available.
- Preserve blocked/partial statuses and claim boundaries.

Verification:
- Identify which artifacts were refreshed and which were intentionally left stale/external-blocked.
- Run focused tests for changed builders.
- Run relevant readiness/freshness checks and confirm source-commit mismatch count is reduced.
