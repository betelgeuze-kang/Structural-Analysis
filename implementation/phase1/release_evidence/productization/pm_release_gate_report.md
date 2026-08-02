# PM Release Gate

- `summary_line`: `PM release gate: BLOCKED | source_provenance=BLOCKED | computed_without_provenance=PM release gate: BLOCKED | release_areas=BLOCKED | paid_pilot_candidate=False | milestones=2/5 | release_areas_green=4/16 | measured_cases=304`
- `recommended_scope`: Release blocked until every source input is reproducible from the declared commit. Any disclosed dependency cycle also requires a separate DAG redesign.
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
- `blocked_release_count`: `66`
- `first_blocker`: `source_provenance::input_not_reproducible_at_declared_commit`
- `operator_action_count`: `74`
- `approval_token_count`: `5`
- `stale_artifact_count`: `27`
- `evidence_surface_count`: `8`
- `missing_evidence_surface_count`: `0`
- `locked_evidence_surface_count`: `0`
- `public_benchmark_ready`: `False`
- `next_locally_closable_gaps`: `G1`

| Milestone | Status | Blockers |
|---|---|---|
| M1 Residual Release Hardening | pass | none |
| M2 Core Engine Depth Closure | blocked | element_material_breadth_gate_not_green, contact_material_coupled_case_count_lt_10_or_missing, rc_steel_composite_material_family_missing, structural_contact_contract_missing, ssi_foundation_link_missing_from_core_summary, panel_contact_failure_reason_code_missing, nonlinear_residual_integrated_case_missing |
| M3 Strict Runtime Closure | blocked | require_hip_failed_without_cpu_only_product_mode, device_residency_below_target |
| M4 Benchmark Breadth Expansion | pass | none |
| M5 Commercial Packaging | blocked | workflow_productization_gate_not_green, viewer_reviewer_customer_preset_missing, pdf_report_or_reviewer_package_missing, audit_trail_action_source_trace_missing, signed_release_registry_missing_or_failed, support_bundle_export_missing_or_failed |

| Release Area | Status | Blockers |
|---|---|---|
| basic_ci Basic CI | blocked | pr_ci_30_consecutive_pass_evidence_missing, nightly_ci_30_consecutive_pass_evidence_missing |
| strict_ci Strict CI | blocked | direct_require_hip_failed_without_cpu_only_scope |
| evidence_freshness Evidence Freshness | blocked | p0_closure_status::producer_newer_than_artifact, p1_readiness_status::producer_newer_than_artifact, p1_benchmark_breadth_status::source_commit_mismatch, p1_benchmark_breadth_status::producer_newer_than_artifact, p1_benchmark_breadth_status::input_dependency_newer_than_artifact, real_project_corpus_measured_status::generated_at_outside_allowed_window, customer_shadow_evidence_status::input_dependency_newer_than_artifact, customer_shadow_evidence_intake_packet::producer_newer_than_artifact, fresh_full_validation_lane_status::source_commit_mismatch, fresh_full_validation_lane_status::producer_newer_than_artifact, fresh_full_validation_lane_status::input_dependency_newer_than_artifact, g1_direct_residual_terminal_gate_report::source_commit_mismatch, g1_direct_residual_terminal_gate_report::producer_newer_than_artifact, g1_shell_material_budgeted_continuation_status::source_commit_mismatch, g1_shell_material_budgeted_continuation_status::producer_newer_than_artifact, g1_shell_material_budgeted_continuation_status::input_dependency_newer_than_artifact, evidence_console_scope_status::source_commit_mismatch, evidence_console_scope_status::producer_newer_than_artifact, evidence_console_scope_status::input_dependency_newer_than_artifact, developer_preview_rc_status::producer_newer_than_artifact, developer_preview_rc_status::input_dependency_newer_than_artifact, accuracy_parity_scorecard::source_commit_mismatch, accuracy_parity_scorecard::producer_newer_than_artifact, accuracy_parity_scorecard::input_dependency_newer_than_artifact, product_production_ai_checkpoint_readiness::source_commit_mismatch, product_production_ai_checkpoint_readiness::producer_newer_than_artifact, product_production_ai_checkpoint_readiness::input_dependency_newer_than_artifact |
| core_engine Core Engine | blocked | core_depth_milestone_not_green, commercial_readiness_contract_not_green, commercial_accuracy_contract_not_green |
| ndtha NDTHA | pass | none |
| residual Residual | pass | none |
| benchmark_breadth Benchmark Breadth | pass | none |
| runtime Runtime | blocked | strict_runtime_milestone_not_green |
| memory Memory | pass | none |
| gpu_device GPU / Device | blocked | gpu_strict_failed_without_cpu_only_scope, device_residency_target_not_met |
| interop Interop | blocked | midas_interop_not_green, midas_native_roundtrip_not_green, midas_exact_roundtrip_not_green, kds_full_crosswalk_not_green |
| report Report | blocked | commercial_packaging_milestone_not_green, reviewer_package_auto_not_green, repro_command_missing_from_report_evidence, reproducibility_lock_not_green |
| ux UX | blocked | human_new_user_observation_missing_or_failed, human_new_user_30min_sample_evidence_missing |
| support Support | blocked | failure_bundle_export_not_green |
| security Security | blocked | license_status_not_configured, repro_build_not_green |
| github_sync GitHub Development Sync | blocked | github_sync_preflight::local_head_mismatch |
