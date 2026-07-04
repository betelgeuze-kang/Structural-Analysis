# PocketMD Lite Source Acquisition Plan

- `status`: `ready`
- `contract_pass`: `True`
- `actual_closure_ready`: `True`
- `blocker_count`: `0`
- `phase4_refinement_receipt_plan_status`: `operator_receipts_required`
- `phase4_refinement_receipt_role_count`: `4`
- `refinement_execution_plan`: `implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `refinement_execution_plan_status`: `operator_refinement_rows_required`
- `required_candidate_slot_count`: `6`
- `phase4_candidate_slot_matrix_count`: `6`
- `phase4_missing_candidate_slot_count`: `0`
- `phase4_metric_closure_matrix_count`: `8`
- `phase4_completion_audit_status`: `ready`
- `phase4_completion_ready_requirement_count`: `9`
- `phase4_completion_blocked_requirement_count`: `0`
- `phase4_actual_evidence_audit_status`: `ready`
- `phase4_actual_evidence_blocked_component_count`: `0`
- `phase4_actual_operator_blocker_family_count`: `8`
- `phase4_actual_operator_blocker_family_missing_item_count`: `0`
- `survival_report_status`: `ready`
- `survival_report_blocker_count`: `0`
- `template_preflight_status`: `operator_rows_completion_required`
- `template_preflight_role_receipt_blocked_count`: `24`
- `template_preflight_operator_input_source_receipt_blocked_count`: `5`
- `rows_from_receipt_bundle_report_status`: `rows_materialized`
- `rows_from_receipt_bundle_ready_receipt_count`: `6`
- `rows_from_receipt_bundle_metric_family_blocked_count`: `0`
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
| 10 | `materialize_completed_template_to_pocketmd_lite_topk_rows` |
| 11 | `run_pocketmd_lite_raw_row_importer_and_survival_materializer` |
| 12 | `refresh_science_actual_closure_from_rows` |

## Phase 4 Completion Audit

- `status`: `ready`
- `actual_closure_ready`: `True`
- `remaining_row_inputs`: ``
- `remaining_operator_action`: `run_pocketmd_lite_raw_row_importer_and_survival_materializer`

| Requirement | Product Requirement | Status | Pass | Blockers |
|---|---|---|---|---|
| `bounded_top_k_scope_contract` | PocketMD Lite applies only to upstream top-k candidates | `ready` | `True` | `none` |
| `top_k_refinement_rows_present` | top-k candidate refinement rows are present | `ready` | `True` | `none` |
| `top_k_refinement_case_coverage` | top-k candidate case/rank coverage is complete | `ready` | `True` | `none` |
| `local_min_survival_reported` | local-min survival is reported | `ready` | `True` | `none` |
| `contact_persistence_reported` | contact persistence is reported | `ready` | `True` | `none` |
| `h_bond_persistence_reported` | H-bond persistence is reported | `ready` | `True` | `none` |
| `clash_relief_reported` | clash relief is reported | `ready` | `True` | `none` |
| `uncertainty_reported` | uncertainty interval summary is reported | `ready` | `True` | `none` |
| `broad_all_atom_fep_claims_locked` | broad all-atom MD/FEP claims remain locked | `ready` | `True` | `none` |

## Phase 4 Actual Evidence Audit

- `status`: `ready`
- `actual_closure_ready`: `True`
- `remaining_evidence`: ``
- `role_receipt_blocked_count`: `24`
- `operator_input_source_receipt_blocked_count`: `5`
- `missing_metric_count`: `0`
- `operator_blocker_family_count`: `8`
- `operator_blocker_family_missing_item_count`: `0`

| Component | Status | Pass | Current | Required | Blockers |
|---|---|---|---|---|---|
| `bounded_top_k_row_slots` | `ready` | `True` | `{"covered_required_slot_count": 6, "missing_required_slot_count": 0, "raw_row_candidate_status": "row_artifact_detected_validated", "required_candidate_slot_count": 6}` | `{"coverage_ready": true, "required_candidate_slot_count": 6}` | `none` |
| `per_candidate_role_receipts` | `ready` | `True` | `{"receipt_bundle_incomplete_receipt_count": 0, "receipt_bundle_ready_receipt_count": 6, "receipt_bundle_rows_materialized": true, "role_receipt_blocked_count": 24, "role_receipt_plan_count": 24, "template_preflight_status": "operator_rows_completion_required"}` | `{"receipt_bundle_incomplete_receipt_count": 0, "receipt_bundle_ready_receipt_count": 6, "role_receipt_blocked_count": 0, "role_receipt_plan_count": 24}` | `none` |
| `operator_input_source_receipt` | `ready` | `True` | `{"receipt_bundle_incomplete_receipt_count": 0, "receipt_bundle_ready_receipt_count": 6, "receipt_bundle_rows_materialized": true, "survival_report_receipt_blocker_count": 0, "survival_report_receipt_contract_pass": true, "survival_report_receipt_status": "pass", "template_preflight_blocked_count": 5, "template_preflight_requirement_count": 5}` | `{"receipt_bundle_incomplete_receipt_count": 0, "receipt_bundle_ready_receipt_count": 6, "survival_report_receipt_contract_pass": true, "template_preflight_blocked_count": 0, "template_preflight_requirement_count": 5}` | `none` |
| `survival_metric_summary` | `ready` | `True` | `{"reported_metric_count": 5, "required_metric_count": 5, "survival_report_contract_pass": true, "survival_report_status": "ready"}` | `{"missing_metric_count": 0, "required_metric_count": 5, "survival_report_contract_pass": true}` | `none` |

### Operator Blocker Families

| Family | Status | Missing Items | Blocked Cases | Operator Action | Command Key |
|---|---|---:|---:|---|---|
| `top_k_candidate_rows` | `ready` | 0 | 0 | `attach_pocketmd_lite_topk_rows_at_default_dropzone` | `materialize_rows_from_receipt_bundle` |
| `per_candidate_role_receipts` | `ready` | 0 | 0 | `complete_pocketmd_per_candidate_role_receipts` | `build_row_template_preflight` |
| `operator_input_source_receipt` | `ready` | 0 | 0 | `complete_pocketmd_operator_input_source_receipt` | `build_row_template_preflight` |
| `local_min_survival` | `ready` | 0 | 0 | `review_metric_family_receipts` | `materialize_rows_from_receipt_bundle` |
| `contact_persistence` | `ready` | 0 | 0 | `review_metric_family_receipts` | `materialize_rows_from_receipt_bundle` |
| `h_bond_persistence` | `ready` | 0 | 0 | `review_metric_family_receipts` | `materialize_rows_from_receipt_bundle` |
| `clash_relief` | `ready` | 0 | 0 | `review_metric_family_receipts` | `materialize_rows_from_receipt_bundle` |
| `uncertainty` | `ready` | 0 | 0 | `review_metric_family_receipts` | `materialize_rows_from_receipt_bundle` |

| Case | Minimum Rows | Required Rank Prefix | Scope |
|---|---:|---|---|
| `pocketmd_lite_case_001` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_002` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_003` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |

## Phase 4 Candidate Slot Matrix

| Slot | Case | Rank | Status | Required Metric Fields |
|---|---|---|---|---|
| `pocketmd_lite_case_001_rank_1` | `pocketmd_lite_case_001` | `1` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_001_rank_2` | `pocketmd_lite_case_001` | `2` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_002_rank_1` | `pocketmd_lite_case_002` | `1` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_002_rank_2` | `pocketmd_lite_case_002` | `2` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_003_rank_1` | `pocketmd_lite_case_003` | `1` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |
| `pocketmd_lite_case_003_rank_2` | `pocketmd_lite_case_003` | `2` | `provided` | `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit` |

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

## Commands

- `write_plan`: `python3 scripts/build_pocketmd_lite_source_acquisition_plan.py`
- `review_row_template`: `sed -n '1,20p' implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `build_row_template_preflight`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `materialize_rows_from_template`: `python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py --template implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv --out-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_from_template_report.json --fail-blocked`
- `materialize_rows_from_receipt_bundle`: `python3 scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py --receipt-bundle implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_receipt_bundle.json --out-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_from_receipt_bundle_report.json --fail-blocked`
- `build_refinement_execution_plan`: `python3 scripts/build_pocketmd_lite_refinement_execution_plan.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`

This plan records the row, metric, and receipt contract needed to acquire PocketMD Lite top-k refinement evidence. It does not synthesize rows, run Lite refinement, infer missing metrics, or unlock broad all-atom MD/FEP claims before the materializer verifies real operator evidence.
