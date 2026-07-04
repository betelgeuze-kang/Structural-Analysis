# PocketMD Lite Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `actual_closure_ready`: `False`
- `blocker_count`: `3`
- `phase4_refinement_receipt_plan_status`: `operator_receipts_required`
- `phase4_refinement_receipt_role_count`: `4`
- `refinement_execution_plan`: `implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `refinement_execution_plan_status`: `operator_refinement_rows_required`
- `required_candidate_slot_count`: `6`
- `phase4_candidate_slot_matrix_count`: `6`
- `phase4_missing_candidate_slot_count`: `6`
- `phase4_metric_closure_matrix_count`: `8`
- `template_preflight_status`: `operator_rows_completion_required`
- `template_preflight_role_receipt_blocked_count`: `24`
- `template_preflight_operator_input_source_receipt_blocked_count`: `5`
- `row_template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`

## Operator Next Actions

| Step | Action |
|---:|---|
| 1 | `review_phase4_refinement_receipt_plan` |
| 2 | `build_pocketmd_lite_refinement_execution_plan` |
| 3 | `build_pocketmd_lite_topk_rows_template_preflight` |
| 4 | `select_upstream_ranked_top_k_candidate_sets` |
| 5 | `attach_upstream_top_k_provenance_and_checksum_for_every_candidate` |
| 6 | `run_bounded_lite_refinement_for_top_k_candidates_only` |
| 7 | `write_local_min_contact_hbond_clash_uncertainty_rows` |
| 8 | `attach_row_source_receipts_with_license_url_and_artifact_sha256` |
| 9 | `write_pocketmd_lite_topk_rows_at_default_dropzone` |
| 10 | `run_pocketmd_lite_raw_row_importer_and_survival_materializer` |
| 11 | `refresh_science_actual_closure_from_rows` |

| Case | Minimum Rows | Required Rank Prefix | Scope |
|---|---:|---|---|
| `pocketmd_lite_case_001` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_002` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_003` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |

## Phase 4 Candidate Slot Matrix

| Slot | Case | Rank | Status | Required Metric Fields |
|---|---|---|---|---|
| `pocketmd_lite_case_001_rank_1` | `pocketmd_lite_case_001` | `1` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_001_rank_2` | `pocketmd_lite_case_001` | `2` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_002_rank_1` | `pocketmd_lite_case_002` | `1` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_002_rank_2` | `pocketmd_lite_case_002` | `2` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_003_rank_1` | `pocketmd_lite_case_003` | `1` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_003_rank_2` | `pocketmd_lite_case_003` | `2` | `missing` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |

## Phase 4 Metric Closure Matrix

| Criterion | Metric | Status | Required Fields | Receipt Roles |
|---|---|---|---|---|
| `top_k_refinement_rows_present` | `` | `blocked` | `row_coverage_and_receipts` | `upstream_top_k_candidate_scope_receipt` |
| `top_k_refinement_case_coverage` | `` | `blocked` | `row_coverage_and_receipts` | `upstream_top_k_candidate_scope_receipt` |
| `local_min_survival_materialized` | `local_min_survival_rate` | `blocked` | `local_min_survived` | `lite_refinement_run_receipt` |
| `contact_persistence_materialized` | `contact_persistence_rate` | `blocked` | `contact_persistence_rate` | `interaction_persistence_receipt` |
| `h_bond_persistence_materialized` | `h_bond_persistence_rate` | `blocked` | `h_bond_persistence_rate` | `interaction_persistence_receipt` |
| `clash_relief_materialized` | `clash_relief_rate` | `blocked` | `clash_count_before`, `clash_count_after` | `interaction_persistence_receipt` |
| `uncertainty_summary_materialized` | `uncertainty_width_median` | `blocked` | `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` | `uncertainty_interval_receipt` |
| `report_blockers_resolved` | `` | `blocked` | `row_coverage_and_receipts` | `lite_refinement_run_receipt`, `interaction_persistence_receipt`, `uncertainty_interval_receipt` |

## Phase 4 Receipt Roles

| Receipt Role | Source Role | Closes Criteria |
|---|---|---|
| `upstream_top_k_candidate_scope_receipt` | `upstream_ranked_top_k_candidate_set` | `top_k_refinement_rows_present`, `top_k_refinement_case_coverage` |
| `lite_refinement_run_receipt` | `bounded_lite_refinement_run` | `local_min_survival_materialized`, `report_blockers_resolved` |
| `interaction_persistence_receipt` | `contact_hbond_clash_metric_rows` | `contact_persistence_materialized`, `h_bond_persistence_materialized`, `clash_relief_materialized`, `report_blockers_resolved` |
| `uncertainty_interval_receipt` | `candidate_uncertainty_interval_rows` | `uncertainty_summary_materialized`, `report_blockers_resolved` |

## Missing Row Input Actions

| Row Input | Action | Default Artifact | Required Slots |
|---|---|---|---:|
| `pocketmd_rows` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | 6 |

### PocketMD Row Preflight Action

- `status`: `row_artifact_missing`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`
- `template_preflight_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json`
- `template_preflight_markdown_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `build_template_preflight_command`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `supported_candidate_paths`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.jsonl`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.ndjson`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.csv`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.tsv`
- `detected_row_artifact_count`: `0`
- `selected_path`: ``
- `validated_row_count`: `0`
- `covered_required_slot_count`: `0/6`
- `missing_required_slot_count`: `6`
- `validation_error`: ``
- `blocker`: `pocketmd_lite_topk_rows_not_acquired`
- `template_preflight_role_receipt_blocked_count`: `24`
- `template_preflight_operator_input_source_receipt_blocked_count`: `5`
- `import_rows_command`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `verify_science_actual_closure_command`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`
- `operator_rows_must_be_real_top_k_refinement_outputs`: `True`
- `preflight_does_not_run_refinement`: `True`

### PocketMD Top-k Rows Action

- `status`: `operator_rows_required`
- `template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `template_preflight_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json`
- `build_template_preflight_command`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`
- `review_template_command`: `sed -n '1,20p' implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `import_rows_command`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival_command`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `verify_science_actual_closure_command`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`
- `operator_must_fill_or_verify`: `case_id`, `source_family`, `top_k_rank`, `candidate_id`, `upstream_top_k_provenance_ref`, `upstream_top_k_source_checksum`, `pre_refinement_energy_proxy`, `post_refinement_energy_proxy`, `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit`, `provenance_ref`, `source_checksum`, `operator_input_source.source_artifact`, `operator_input_source.source_artifact_sha256`, `operator_input_source.source_id`, `operator_input_source.source_url`, `operator_input_source.source_license`
- `required_receipt_roles`: `upstream_top_k_candidate_scope_receipt`, `lite_refinement_run_receipt`, `interaction_persistence_receipt`, `uncertainty_interval_receipt`
- `role_receipt_blocked_count`: `24`
- `first_blocked_role_receipt`: `upstream_top_k_candidate_scope_receipt` / `pocketmd_lite_case_001_rank_01`
- `operator_input_source_receipt_blocked_count`: `5`
- `first_blocked_operator_input_source_receipt`: `source_id`
- `phase4_metric_receipt_action_count`: `8`
- `template_is_not_evidence`: `True`
- `placeholder_or_fixture_rows_do_not_promote`: `True`
- `summary_only_metrics_do_not_promote`: `True`

#### PocketMD Phase 4 Receipt Closure Actions

| Criterion | Metric | Receipt Roles | Required Row Fields | Blockers |
|---|---|---|---|---|
| `top_k_refinement_rows_present` | `` | `upstream_top_k_candidate_scope_receipt` | `none` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `top_k_refinement_case_coverage` | `` | `upstream_top_k_candidate_scope_receipt` | `none` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `local_min_survival_materialized` | `local_min_survival_rate` | `lite_refinement_run_receipt` | `local_min_survived` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `contact_persistence_materialized` | `contact_persistence_rate` | `interaction_persistence_receipt` | `contact_persistence_rate` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `h_bond_persistence_materialized` | `h_bond_persistence_rate` | `interaction_persistence_receipt` | `h_bond_persistence_rate` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `clash_relief_materialized` | `clash_relief_rate` | `interaction_persistence_receipt` | `clash_count_before`, `clash_count_after` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `uncertainty_summary_materialized` | `uncertainty_width_median` | `uncertainty_interval_receipt` | `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |
| `report_blockers_resolved` | `` | `lite_refinement_run_receipt`, `interaction_persistence_receipt`, `uncertainty_interval_receipt` | `none` | `pocketmd_lite_topk_rows_not_acquired`, `upstream_top_k_candidate_receipts_not_attached`, `lite_refinement_metric_receipts_not_attached` |

## Commands

- `write_plan`: `python3 scripts/build_pocketmd_lite_source_acquisition_plan.py`
- `review_row_template`: `sed -n '1,20p' implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `build_row_template_preflight`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `build_refinement_execution_plan`: `python3 scripts/build_pocketmd_lite_refinement_execution_plan.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`

This plan records the row, metric, and receipt contract needed to acquire PocketMD Lite top-k refinement evidence. It does not synthesize rows, run Lite refinement, infer missing metrics, or unlock broad all-atom MD/FEP claims before the materializer verifies real operator evidence.
