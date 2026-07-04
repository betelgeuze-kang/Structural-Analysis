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
- `row_template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`

| Case | Minimum Rows | Required Rank Prefix | Scope |
|---|---:|---|---|
| `pocketmd_lite_case_001` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_002` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_003` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |

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
- `supported_candidate_paths`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.jsonl`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.ndjson`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.csv`, `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.tsv`
- `detected_row_artifact_count`: `0`
- `selected_path`: ``
- `validated_row_count`: `0`
- `covered_required_slot_count`: `0/6`
- `missing_required_slot_count`: `6`
- `validation_error`: ``
- `blocker`: `pocketmd_lite_topk_rows_not_acquired`
- `import_rows_command`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `verify_science_actual_closure_command`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`
- `operator_rows_must_be_real_top_k_refinement_outputs`: `True`
- `preflight_does_not_run_refinement`: `True`

### PocketMD Top-k Rows Action

- `status`: `operator_rows_required`
- `template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`
- `review_template_command`: `sed -n '1,20p' implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `import_rows_command`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival_command`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `verify_science_actual_closure_command`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`
- `operator_must_fill_or_verify`: `case_id`, `source_family`, `top_k_rank`, `candidate_id`, `upstream_top_k_provenance_ref`, `upstream_top_k_source_checksum`, `pre_refinement_energy_proxy`, `post_refinement_energy_proxy`, `local_min_survived`, `contact_persistence_rate`, `h_bond_persistence_rate`, `clash_count_before`, `clash_count_after`, `uncertainty_low`, `uncertainty_high`, `uncertainty_unit`, `provenance_ref`, `source_checksum`, `operator_input_source.source_artifact`, `operator_input_source.source_artifact_sha256`, `operator_input_source.source_id`, `operator_input_source.source_url`, `operator_input_source.source_license`
- `required_receipt_roles`: `upstream_top_k_candidate_scope_receipt`, `lite_refinement_run_receipt`, `interaction_persistence_receipt`, `uncertainty_interval_receipt`
- `template_is_not_evidence`: `True`
- `placeholder_or_fixture_rows_do_not_promote`: `True`
- `summary_only_metrics_do_not_promote`: `True`

## Commands

- `write_plan`: `python3 scripts/build_pocketmd_lite_source_acquisition_plan.py`
- `review_row_template`: `sed -n '1,20p' implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `build_refinement_execution_plan`: `python3 scripts/build_pocketmd_lite_refinement_execution_plan.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`

This plan records the row, metric, and receipt contract needed to acquire PocketMD Lite top-k refinement evidence. It does not synthesize rows, run Lite refinement, infer missing metrics, or unlock broad all-atom MD/FEP claims before the materializer verifies real operator evidence.
