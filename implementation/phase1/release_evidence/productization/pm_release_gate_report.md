# PM Release Gate

- `summary_line`: `PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=11/16 | measured_cases=304`
- `recommended_scope`: Limited milestone evidence is green, but the broader PM release-area gate is still blocked; keep any use constrained to the paid-pilot scope guard until release-area blockers are closed.
- `paid_pilot_candidate`: `True`
- `limited_commercial_milestone_ready`: `True`
- `limited_commercial_ready`: `False`
- `limited_commercial_release_ready`: `False`
- `release_area_gate_ready`: `False`
- `full_release_gate_ready`: `False`
- `ga_enterprise_ready`: `False`
- `cursor_opencode_worker_preflight_pass`: `True`
- `full_gap_ledger_status`: `open`
- `commercial_gap_status`: `open`
- `commercial_solver_gap_ready`: `False`
- `ai_engine_gap_ready`: `False`
- `release_allowed`: `False`
- `blocked_release_count`: `21`
- `first_blocker`: `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`
- `operator_action_count`: `25`
- `stale_artifact_count`: `12`
- `evidence_surface_count`: `8`
- `locked_evidence_surface_count`: `0`
- `public_benchmark_ready`: `True`
- `broad_gpcr_family_claim_safe`: `False`
- `next_locally_closable_gaps`: `G1`

| Milestone | Status | Blockers |
|---|---|---|
| M1 Residual Release Hardening | pass | none |
| M2 Core Engine Depth Closure | pass | none |
| M3 Strict Runtime Closure | pass | none |
| M4 Benchmark Breadth Expansion | pass | none |
| M5 Commercial Packaging | pass | none |

| Release Area | Status | Blockers |
|---|---|---|
| basic_ci Basic CI | blocked | pr_ci_30_consecutive_pass_evidence_missing, nightly_ci_30_consecutive_pass_evidence_missing |
| strict_ci Strict CI | pass | none |
| evidence_freshness Evidence Freshness | blocked | p1_benchmark_breadth_status::input_dependency_newer_than_artifact, customer_shadow_evidence_intake_packet::source_commit_mismatch, fresh_full_validation_lane_status::source_commit_mismatch, fresh_full_validation_lane_status::input_dependency_newer_than_artifact, evidence_console_scope_status::source_commit_mismatch, evidence_console_scope_status::input_dependency_newer_than_artifact, accuracy_parity_scorecard::generated_at_outside_allowed_window, accuracy_parity_scorecard::source_commit_missing, accuracy_parity_scorecard::engine_version_missing, accuracy_parity_scorecard::input_checksum_missing, accuracy_parity_scorecard::reuse_marker_missing, accuracy_parity_scorecard::producer_newer_than_artifact |
| core_engine Core Engine | pass | none |
| ndtha NDTHA | pass | none |
| residual Residual | pass | none |
| benchmark_breadth Benchmark Breadth | pass | none |
| runtime Runtime | pass | none |
| memory Memory | pass | none |
| gpu_device GPU / Device | pass | none |
| interop Interop | pass | none |
| report Report | pass | none |
| ux UX | blocked | human_new_user_observation_missing_or_failed, human_new_user_30min_sample_evidence_missing |
| support Support | pass | none |
| security Security | blocked | license_status_not_configured |
| github_sync GitHub Development Sync | blocked | github_sync_preflight::worktree_not_clean, github_sync_preflight::remote_mutation_approval_required, github_sync_remote_sync_pending, github_sync_preflight_not_synced |
