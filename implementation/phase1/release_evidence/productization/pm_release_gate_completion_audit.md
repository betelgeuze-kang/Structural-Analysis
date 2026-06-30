# PM Release Gate Completion Audit

- `summary_line`: `PM release gate completion audit: BLOCKED | requirements=52 | pass=46 | blocked=6`
- `pm_summary_line`: `PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=12/16 | measured_cases=304`
- `contract_pass`: `False`
- `explicit_requirement_count`: `52`
- `blocked_requirement_count`: `6`
- `blocked_release_area_next_action_missing_count`: `0`

| Requirement | Group | Status | Blockers | Next Action |
|---|---|---|---|---|
| `release_area.basic_ci` PR/nightly 30 consecutive PASS evidence | `release_area` | `blocked_external_owner_input_ready` | `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`, `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` | basic_ci::pr_ci_30_consecutive_pass_evidence_missing: Collect 30 additional consecutive successful PR CI run(s); keep the pull_request CI lane green and refresh github_actions_ci_streak_evidence before release signoff.; basic_ci::nightly_ci_30_consecutive_pass_evidence_missing: Collect 30 additional consecutive successful nightly CI run(s); keep the scheduled/nightly lane green and refresh github_actions_ci_streak_evidence before release signoff. |
| `release_area.strict_ci` require NDTHA and require HIP or explicit CPU product mode | `release_area` | `pass` | none | none |
| `release_area.evidence_freshness` release evidence generated_at/source commit/engine version/input checksum/reuse marker and producer recency | `release_area` | `pass` | none | none |
| `release_area.core_engine` family p95 error within Limited/GA budget | `release_area` | `pass` | none | none |
| `release_area.ndtha` no collapse false-pass, all converged, long profile pass | `release_area` | `pass` | none | none |
| `release_area.residual` hard and recommended residual pass with fallback limits | `release_area` | `pass` | none | none |
| `release_area.benchmark_breadth` Paid Pilot/Limited/GA validation case breadth | `release_area` | `pass` | none | none |
| `release_area.runtime` p95 runtime budget exceed rate within budget | `release_area` | `pass` | none | none |
| `release_area.memory` OOM zero and peak memory budget report | `release_area` | `pass` | none | none |
| `release_area.gpu_device` release mode CPU fallback forbidden or scoped CPU-only product mode | `release_area` | `pass` | none | none |
| `release_area.interop` MIDAS/KDS/OpenSees roundtrip trace evidence | `release_area` | `pass` | none | none |
| `release_area.report` reviewer package and reproduction commands | `release_area` | `pass` | none | none |
| `release_area.ux` new user completes sample project within 30 minutes | `release_area` | `blocked_external_owner_input_ready` | `ux::human_new_user_observation_missing_or_failed`, `ux::human_new_user_30min_sample_evidence_missing` | 2 blockers: Attach a human new-user observation record for the sample project workflow, including participant status, observer, all five workflow steps (Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report), timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision. |
| `release_area.support` known issues, failure bundle, and rollback evidence | `release_area` | `pass` | none | none |
| `release_area.security` secrets/license/SBOM/repro build pass | `release_area` | `blocked_external_owner_input_ready` | `security::license_status_not_configured` | security::license_status_not_configured: Populate license_status.json from an approved product/legal decision, including approver role, approval timestamp, retrievable evidence reference, scoped product boundary, and no template placeholders before release-area security can pass. |
| `release_area.github_sync` read-only GitHub sync preflight is clean or explicitly approved | `release_area` | `blocked_external_owner_input_ready` | `github_sync::github_sync_preflight::remote_mutation_approval_required`, `github_sync::github_sync_remote_sync_pending`, `github_sync::github_sync_preflight_not_synced` | 3 blockers: Feature branch is synced to the release HEAD. Obtain explicit R4 approval phrase `feature push + main fast-forward 승인` for the remaining main fast-forward, then run the pending main remote-update command from `check_github_development_sync_preflight.py --fetch --json`. |
| `m1_residual_report_fixed` ndtha_residual_gate_report.json fixed in release evidence | `milestone` | `pass` | none | none |
| `m1_recommended_residual_hard_fail` recommended residual hard-fails in strict mode | `milestone` | `pass` | none | none |
| `m1_strict_recommended_residual_pass` strict recommended residual pass | `milestone` | `pass` | none | none |
| `m1_fallback_rate_limited` fallback rate <= 5% | `milestone` | `pass` | none | none |
| `m1_residual_source_solver_raw` solver_raw residual source ratio is reported | `milestone` | `pass` | none | none |
| `m1_normalized_residual` normalized residual is present | `milestone` | `pass` | none | none |
| `m1_corrected_state_recompute` corrected-state recompute after GNN correction | `milestone` | `pass` | none | none |
| `m2_contact_material_cases` contact-material coupled case count >= 10 | `milestone` | `pass` | none | none |
| `m2_rc_steel_composite_contact` RC/steel/composite/contact appear in one report | `milestone` | `pass` | none | none |
| `m2_steel_material_present` steel material evidence present | `milestone` | `pass` | none | none |
| `m2_composite_material_present` composite material evidence present | `milestone` | `pass` | none | none |
| `m2_structural_contact_present` structural contact evidence present | `milestone` | `pass` | none | none |
| `m2_ssi_foundation_link` SSI/foundation link included in core summary | `milestone` | `pass` | none | none |
| `m2_panel_contact_reason_code` panel/contact failure mode reason_code separated | `milestone` | `pass` | none | none |
| `m2_nonlinear_residual_same_case` nonlinear and residual pass in the same case | `milestone` | `pass` | none | none |
| `m3_require_ndtha` require_ndtha passes | `milestone` | `pass` | none | none |
| `m3_require_hip_or_cpu_scope` require_hip passes or CPU-only product mode is declared | `milestone` | `pass` | none | none |
| `m3_cpu_fallback_forbidden` release-mode CPU fallback is forbidden | `milestone` | `pass` | none | none |
| `m3_device_residency` device residency target is explicit and met | `milestone` | `pass` | none | none |
| `m3_host_copy_share` host copy share <= 5% | `milestone` | `pass` | none | none |
| `m4_validation_cases` total validation cases >= 100 | `milestone` | `pass` | none | none |
| `m4_structure_families` structure families >= 5 | `milestone` | `pass` | none | none |
| `m4_holdout_cases` holdout cases exist per family | `milestone` | `pass` | none | none |
| `m4_worst_case_report` worst-case report generated | `milestone` | `pass` | none | none |
| `m4_measured_open_data_split` measured/open data split from fixtures | `milestone` | `pass` | none | none |
| `m5_viewer_mode` reviewer/customer viewer preset | `milestone` | `pass` | none | none |
| `m5_pdf_or_reviewer_package` PDF/report or reviewer package generated | `milestone` | `pass` | none | none |
| `m5_audit_trail` audit trail has action and source row trace | `milestone` | `pass` | none | none |
| `m5_signed_release_registry` release registry is signed | `milestone` | `pass` | none | none |
| `m5_support_bundle_export` support bundle one-click export passes | `milestone` | `pass` | none | none |
| `m5_validation_manual` validation manual is present and complete | `milestone` | `pass` | none | none |
| `m5_limitation_manual` limitation manual is present and complete | `milestone` | `pass` | none | none |
| `release_tier.technical_paid_pilot_candidate` limited milestone evidence supports only a constrained paid pilot candidate | `release_tier` | `pass` | none | none |
| `release_tier.paid_pilot_scope_guard_pass` paid pilot use is constrained by the scope guard and evidence-package references | `release_tier` | `pass` | none | none |
| `release_tier.limited_commercial_full_gate_ready` Limited Commercial release requires full release-area gate readiness | `release_tier` | `blocked` | `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`, `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing`, `ux::human_new_user_observation_missing_or_failed`, `ux::human_new_user_30min_sample_evidence_missing`, `security::license_status_not_configured`, `github_sync::github_sync_preflight::remote_mutation_approval_required`, `github_sync::github_sync_remote_sync_pending`, `github_sync::github_sync_preflight_not_synced` | Close all release-area blockers, regenerate the PM release gate, and verify `release_tiers.limited_commercial_full_gate_ready == true` before Limited Commercial promotion. |
| `release_tier.ga_enterprise_evidence_gate_pass` GA/Enterprise requires independent V&V, family signoff, customer audit/failure bundle, and SLA evidence | `release_tier` | `blocked` | `independent_vv_missing`, `family_validation_manual_signoff_missing`, `customer_audit_failure_bundle_sla_missing`, `customer_shadow::completed_shadow_case_count_below_minimum`, `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`, `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing`, `ux::human_new_user_observation_missing_or_failed`, `ux::human_new_user_30min_sample_evidence_missing`, `security::license_status_not_configured`, `github_sync::github_sync_preflight::remote_mutation_approval_required`, `github_sync::github_sync_remote_sync_pending`, `github_sync::github_sync_preflight_not_synced` | Attach independent V&V attestation, family validation-manual signoff, and customer audit/failure-bundle/SLA approval evidence before GA/Enterprise release. |

This audit expands the PM release gate into explicit requirements. A blocked row with owner-handoff ready still remains blocked until the required evidence is attached and the PM release gate is regenerated.
