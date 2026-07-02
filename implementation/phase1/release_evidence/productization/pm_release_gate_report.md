# PM Release Gate

- `summary_line`: `PM release gate: BLOCKED | release_areas=BLOCKED | paid_pilot_candidate=False | milestones=4/5 | release_areas_green=11/16 | measured_cases=304`
- `recommended_scope`: Release blocked until core PM gates have green evidence.
- `paid_pilot_candidate`: `False`
- `limited_commercial_milestone_ready`: `False`
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
- `blocked_release_count`: `8`
- `first_blocker`: `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`
- `operator_action_count`: `39`
- `approval_token_count`: `5`
- `stale_artifact_count`: `0`
- `evidence_surface_count`: `8`
- `missing_evidence_surface_count`: `0`
- `locked_evidence_surface_count`: `0`
- `public_benchmark_ready`: `True`
- `next_locally_closable_gaps`: `G1`

| Milestone | Status | Blockers |
|---|---|---|
| M1 Residual Release Hardening | pass | none |
| M2 Core Engine Depth Closure | pass | none |
| M3 Strict Runtime Closure | pass | none |
| M4 Benchmark Breadth Expansion | pass | none |
| M5 Commercial Packaging | blocked | pm_blocker_closure_board_count_mismatch |

| Release Area | Status | Blockers |
|---|---|---|
| basic_ci Basic CI | blocked | pr_ci_30_consecutive_pass_evidence_missing, nightly_ci_30_consecutive_pass_evidence_missing |
| strict_ci Strict CI | pass | none |
| evidence_freshness Evidence Freshness | pass | none |
| core_engine Core Engine | pass | none |
| ndtha NDTHA | pass | none |
| residual Residual | pass | none |
| benchmark_breadth Benchmark Breadth | pass | none |
| runtime Runtime | pass | none |
| memory Memory | pass | none |
| gpu_device GPU / Device | pass | none |
| interop Interop | pass | none |
| report Report | blocked | commercial_packaging_milestone_not_green |
| ux UX | blocked | human_new_user_observation_missing_or_failed, human_new_user_30min_sample_evidence_missing |
| support Support | blocked | pm_blocker_closure_board_count_mismatch |
| security Security | blocked | license_status_not_configured |
| github_sync GitHub Development Sync | pass | none |
