# Science Actual Closure Operator Handoff

- `status`: `operator_rows_required`
- `contract_pass`: `True`
- `science_actual_closure_contract_pass`: `False`
- `missing_slot_count`: `2`
- `slot_count`: `6`
- `blocker_count`: `10`

## Actual Closure Progress

- `status`: `operator_evidence_required`
- `actual_closure_ready`: `False`
- `requirements`: `10/19`
- `blocked_requirement_count`: `9`
- `complete_components`: `1/3`
- `blocked_components`: `public_benchmark_phase2_actual_closure`, `pocketmd_lite_topk_actual_closure`
- `missing_row_inputs`: `vina_gnina_rows`, `pocketmd_rows`

| Row Input | Status | Preferred Path | CSV Starter | Closes Criteria | Action |
| --- | --- | --- | --- | --- | --- |

| Component | Status | Requirements | Missing Rows | Failed Criteria |
| --- | --- | --- | --- | --- |
| `public_benchmark_phase2_actual_closure` | `operator_rows_required` | `4/5` | `vina_gnina_rows` | `vina_gnina_comparison_ready` |
| `gpcr_hard_decoy_actual_closure` | `complete` | `5/5` | `none` | `none` |
| `pocketmd_lite_topk_actual_closure` | `operator_rows_required` | `1/9` | `pocketmd_rows` | `top_k_refinement_rows_present`, `top_k_refinement_case_coverage`, `local_min_survival_materialized`, `contact_persistence_materialized`, `h_bond_persistence_materialized`, `clash_relief_materialized`, `uncertainty_summary_materialized`, `report_blockers_resolved` |
| `subset_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `casf_pdbbind_pose_success_harness_ready` | `review_subset_rows_materialization` |
| `pose_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `review_pose_rows_materialization` |
| `enrichment_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `dud_e_or_lit_pcba_enrichment_ready` | `review_enrichment_rows_materialization` |
| `vina_gnina_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `vina_gnina_comparison_ready` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |
| `gpcr_rows` | `provided` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `review_gpcr_rows_materialization` |
| `pocketmd_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved, broad_all_atom_fep_claims_locked` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` |

## Blocking Input Unblock Plan

| Row Input | Status | Expected Rows | First Step | First Blocked Slot | Preflight Artifacts | Primary Command |
| --- | --- | --- | --- | --- | --- | --- |
| `vina_gnina_rows` | `engine_inputs_required` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `review_public_benchmark_vina_gnina_input_manifest_template_preflight` | `case:casf2016_4llx/fill_vina_gnina_input_manifest_row_for_casf2016_4llx`, `engine:casf2016_4llx/vina/casf2016_4llx_vina_run` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json` | `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md` |
| `pocketmd_rows` | `operator_refinement_rows_required` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `preflight_pocketmd_lite_topk_rows_template` | `candidate:pocketmd_lite_case_001_rank_01/attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01`, `role:upstream_top_k_candidate_scope_receipt/pocketmd_lite_case_001_rank_01`, `source:source_id/attach_operator_input_source_source_id`, `report:top_k_refinement_operator_intake` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json` | `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md` |

## Missing Row Packet

| Row Input | Action | Template | Materialization |
| --- | --- | --- | --- |
| `vina_gnina_rows` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked` |

### Vina/GNINA Engine Run Slots

- `blocked_engine_run_slot_count`: `24`
- `operator_unblock_status`: `engine_inputs_required`
- `missing_engine_ids`: `vina`, `gnina`
- `runtime_readiness_blocker_count`: `124`
- `adapter_row_preflight_status`: `row_artifact_missing`
- `input_manifest_template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `input_manifest_template_preflight_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json`
- `input_manifest_template_preflight_command`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md`

| Engine | Runtime Action | Binary Env | Container Env |
| --- | --- | --- | --- |
| `vina` | `configure_vina_runtime` | `PUBLIC_BENCHMARK_VINA_BIN` | `PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE` |
| `gnina` | `configure_gnina_runtime` | `PUBLIC_BENCHMARK_GNINA_BIN` | `PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE` |

| Slot | Case | Engine | Status | Actions |
| --- | --- | --- | --- | --- |
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `casf2016_4llx` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4llx_vina` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `casf2016_4llx` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4llx_gnina` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `casf2016_5c28` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_5c28_vina` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `casf2016_5c28` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_5c28_gnina` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `casf2016_3uuo` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3uuo_vina` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `casf2016_3uuo` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3uuo_gnina` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `casf2016_3ui7` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3ui7_vina` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `casf2016_3ui7` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3ui7_gnina` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `casf2016_5c2h` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_5c2h_vina` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `casf2016_5c2h` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_5c2h_gnina` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `casf2016_2v00` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_2v00_vina` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `casf2016_2v00` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_2v00_gnina` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `casf2016_3wz8` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3wz8_vina` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `casf2016_3wz8` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3wz8_gnina` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `casf2016_3pww` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3pww_vina` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `casf2016_3pww` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3pww_gnina` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `casf2016_3prs` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3prs_vina` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `casf2016_3prs` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3prs_gnina` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `casf2016_3uri` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3uri_vina` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `casf2016_3uri` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_3uri_gnina` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `casf2016_4m0z` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4m0z_vina` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `casf2016_4m0z` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4m0z_gnina` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `casf2016_4m0y` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y, configure_vina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4m0y_vina` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `casf2016_4m0y` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y, configure_gnina_runtime, attach_vina_gnina_adapter_row_for_casf2016_4m0y_gnina` |
| `pocketmd_rows` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows <pocketmd-lite-topk-rows.csv|tsv|json|jsonl|ndjson> --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked` |

### PocketMD Top-k Candidate Slots

- `operator_unblock_status`: `operator_refinement_rows_required`
- `row_template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `row_template_preflight_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json`
- `row_template_preflight_command`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `row_template_preflight_status`: `operator_rows_completion_required`
- `row_template_preflight_ready`: `False`
- `row_template_preflight_missing_metric_value_count`: `42`
- `row_template_preflight_missing_receipt_value_count`: `24`
- `row_template_preflight_write_command`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `survival_report_status`: `operator_evidence_required`
- `survival_report_contract_pass`: `False`
- `survival_report_first_blocked_target`: `top_k_refinement_operator_intake`
- `survival_report_blocker_count`: `6`
- `survival_report_blockers`: `pocketmd_lite_topk_candidate_rows_missing`, `pocketmd_lite_local_min_survival_rows_missing`, `pocketmd_lite_contact_persistence_rows_missing`, `pocketmd_lite_h_bond_persistence_rows_missing`, `pocketmd_lite_clash_relief_rows_missing`, `pocketmd_lite_uncertainty_rows_missing`
| Slot | Case | Rank | Status | Action |
| --- | --- | --- | --- | --- |
| `pocketmd_lite_case_001_rank_01` | `pocketmd_lite_case_001` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01` |
| `pocketmd_lite_case_001_rank_02` | `pocketmd_lite_case_001` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_02` |
| `pocketmd_lite_case_002_rank_01` | `pocketmd_lite_case_002` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_002_rank_01` |
| `pocketmd_lite_case_002_rank_02` | `pocketmd_lite_case_002` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_002_rank_02` |
| `pocketmd_lite_case_003_rank_01` | `pocketmd_lite_case_003` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_003_rank_01` |
| `pocketmd_lite_case_003_rank_02` | `pocketmd_lite_case_003` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_003_rank_02` |

## Blocked Component Actions

| Component | Row Input | Action | Default Artifact | Source Action | Source Row Action | Source Command | Required Receipts | Source Phase 2 Criteria | Source Phase 4 Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pocketmd_lite_topk_actual_closure` | `pocketmd_rows` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `resolve_pocketmd_lite_source_acquisition_blockers` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>` | `upstream_top_k_candidate_scope_receipt, lite_refinement_run_receipt, interaction_persistence_receipt, uncertainty_interval_receipt` | `` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved` |
| `public_benchmark_phase2_actual_closure` | `vina_gnina_rows` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `resolve_public_benchmark_phase2_source_acquisition_blockers` | `attach_vina_gnina_rows_then_run_phase2_row_audit` | `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json` | `source_license_or_accession, source_checksum, provenance_ref, predicted_ligand_checksum, engine_config_checksum, engine_run_provenance_ref` | `vina_gnina_comparison_ready` | `` |

### Source Acquisition Next Actions

| Component | Row Input | Source Action | First Step | Last Step | Count |
| --- | --- | --- | --- | --- | ---: |
| `pocketmd_lite_topk_actual_closure` | `pocketmd_rows` | `resolve_pocketmd_lite_source_acquisition_blockers` | `review_phase4_refinement_receipt_plan` | `refresh_science_actual_closure_from_rows` | 11 |
| `public_benchmark_phase2_actual_closure` | `vina_gnina_rows` | `resolve_public_benchmark_phase2_source_acquisition_blockers` | `review_official_source_receipt_plan` | `refresh_public_benchmark_source_of_truth` | 14 |

### PocketMD Row Preflight Action

- `component_id`: `pocketmd_lite_topk_actual_closure`
- `row_input_id`: `pocketmd_rows`
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
- `template_preflight_role_receipt_blocked_count`: `24`
- `template_preflight_operator_input_source_receipt_blocked_count`: `5`
- `import_rows_command`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `verify_science_actual_closure_command`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`
- `operator_rows_must_be_real_top_k_refinement_outputs`: `True`
- `preflight_does_not_run_refinement`: `True`

### PocketMD Top-k Rows Action

- `component_id`: `pocketmd_lite_topk_actual_closure`
- `row_input_id`: `pocketmd_rows`
- `status`: `operator_rows_required`
- `template_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`
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

### Vina/GNINA Input Manifest Action

- `component_id`: `public_benchmark_phase2_actual_closure`
- `row_input_id`: `vina_gnina_rows`
- `status`: `operator_manifest_required`
- `template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `expected_manifest_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`
- `default_execution_plan_manifest_path`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.json`
- `recommended_template_dropzone`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`
- `recommended_template_dropzone_is_supported_candidate_path`: `True`
- `accepted_manifest_formats`: `json`, `jsonl`, `ndjson`, `csv`, `tsv`
- `supported_manifest_candidate_paths`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.json`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.jsonl`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.ndjson`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.tsv`
- `detected_manifest_artifact_count`: `0`
- `selected_manifest_path`: ``
- `selected_manifest_format`: ``
- `input_manifest_row_count`: `0`
- `input_manifest_load_errors`: `none`
- `template_to_manifest_command`: `cp implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`
- `verify_execution_plan_command`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `verify_runtime_readiness_command`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `operator_must_fill_or_verify`: `prepared_receptor_path`, `prepared_receptor_checksum`, `prepared_ligand_path`, `prepared_ligand_checksum`, `vina_config_ref`, `gnina_config_ref`, `vina_run_receipt_ref`, `gnina_run_receipt_ref`, `input_preparation_provenance_ref`
- `template_is_not_evidence`: `True`
- `do_not_treat_blank_prepared_checksums_as_ready`: `True`

### Vina/GNINA Adapter Row Preflight Action

- `component_id`: `public_benchmark_phase2_actual_closure`
- `row_input_id`: `vina_gnina_rows`
- `status`: `row_artifact_missing`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`
- `row_template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv`
- `row_template_preflight_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json`
- `build_row_template_preflight_command`: `python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.md`
- `role_receipt_blocked_count`: `72`
- `first_blocked_role_receipt`: `engine_run_artifact_receipt` / `casf2016_4llx_vina_casf2016_4llx_vina_run`
- `supported_candidate_paths`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.jsonl`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.ndjson`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.csv`
- `detected_row_artifact_count`: `0`
- `selected_path`: ``
- `adapter_preflight_status`: `missing`
- `adapter_preflight_blockers`: `none`
- `direct_adapter_materialization_command`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `operator_rows_must_be_real_engine_outputs`: `True`
- `preflight_does_not_run_engines`: `True`

### PocketMD Phase 4 Completion Audit

- `status`: `operator_topk_rows_required`
- `requirements_ready`: `2/9`
- `blocked_requirement_count`: `7`
- `remaining_row_inputs`: `pocketmd_rows`
- `remaining_operator_action`: `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json`
- `remaining_blockers`: `pocketmd_lite_topk_rows_not_acquired`, `pocketmd_lite_topk_candidate_rows_missing`, `pocketmd_lite_local_min_survival_rows_missing`, `pocketmd_lite_contact_persistence_rows_missing`, `pocketmd_lite_h_bond_persistence_rows_missing`, `pocketmd_lite_clash_relief_rows_missing`, `pocketmd_lite_uncertainty_rows_missing`

| Requirement | Status | Product Requirement | Blockers |
|---|---|---|---|
| `bounded_top_k_scope_contract` | `ready` | PocketMD Lite applies only to upstream top-k candidates | `none` |
| `top_k_refinement_rows_present` | `blocked` | top-k candidate refinement rows are present | `pocketmd_lite_topk_rows_not_acquired`, `pocketmd_lite_topk_candidate_rows_missing` |
| `top_k_refinement_case_coverage` | `blocked` | top-k candidate case/rank coverage is complete | `pocketmd_lite_topk_rows_not_acquired`, `pocketmd_lite_topk_candidate_rows_missing` |
| `local_min_survival_reported` | `blocked` | local-min survival is reported | `pocketmd_lite_local_min_survival_rows_missing`, `pocketmd_lite_topk_rows_not_acquired` |
| `contact_persistence_reported` | `blocked` | contact persistence is reported | `pocketmd_lite_contact_persistence_rows_missing`, `pocketmd_lite_topk_rows_not_acquired` |
| `h_bond_persistence_reported` | `blocked` | H-bond persistence is reported | `pocketmd_lite_h_bond_persistence_rows_missing`, `pocketmd_lite_topk_rows_not_acquired` |
| `clash_relief_reported` | `blocked` | clash relief is reported | `pocketmd_lite_clash_relief_rows_missing`, `pocketmd_lite_topk_rows_not_acquired` |
| `uncertainty_reported` | `blocked` | uncertainty interval summary is reported | `pocketmd_lite_uncertainty_rows_missing`, `pocketmd_lite_topk_rows_not_acquired` |
| `broad_all_atom_fep_claims_locked` | `ready` | broad all-atom MD/FEP claims remain locked | `none` |

### PocketMD Actual Evidence Audit

- `status`: `operator_topk_rows_required`
- `actual_closure_ready`: `False`
- `ready_component_count`: `0`
- `blocked_component_count`: `4`
- `remaining_evidence`: `bounded_top_k_row_slots`, `per_candidate_role_receipts`, `operator_input_source_receipt`, `survival_metric_summary`

| Component | Status | Pass | Current | Required | Blockers |
|---|---|---|---|---|---|
| `bounded_top_k_row_slots` | `blocked` | `False` | `{"covered_required_slot_count": 0, "missing_required_slot_count": 6, "raw_row_candidate_status": "row_artifact_missing", "required_candidate_slot_count": 6}` | `{"coverage_ready": true, "required_candidate_slot_count": 6}` | `pocketmd_lite_topk_rows_not_acquired`, `pocketmd_lite_topk_candidate_rows_missing` |
| `per_candidate_role_receipts` | `blocked` | `False` | `{"role_receipt_blocked_count": 24, "role_receipt_plan_count": 24, "template_preflight_status": "operator_rows_completion_required"}` | `{"role_receipt_blocked_count": 0, "role_receipt_plan_count": 24}` | `pocketmd_lite_per_candidate_role_receipts_incomplete` |
| `operator_input_source_receipt` | `blocked` | `False` | `{"survival_report_receipt_blocker_count": 1, "survival_report_receipt_contract_pass": false, "survival_report_receipt_status": "blocked", "template_preflight_blocked_count": 5, "template_preflight_requirement_count": 5}` | `{"survival_report_receipt_contract_pass": true, "template_preflight_blocked_count": 0, "template_preflight_requirement_count": 5}` | `operator_input_source_receipt_required`, `pocketmd_lite_operator_input_source_receipt_incomplete` |
| `survival_metric_summary` | `blocked` | `False` | `{"reported_metric_count": 0, "required_metric_count": 5, "survival_report_contract_pass": false, "survival_report_status": "operator_evidence_required"}` | `{"missing_metric_count": 0, "required_metric_count": 5, "survival_report_contract_pass": true}` | `pocketmd_lite_local_min_survival_rows_missing`, `pocketmd_lite_contact_persistence_rows_missing`, `pocketmd_lite_h_bond_persistence_rows_missing`, `pocketmd_lite_clash_relief_rows_missing`, `pocketmd_lite_uncertainty_rows_missing` |

### Public Benchmark Vina/GNINA Actual Evidence Audit

- `status`: `engine_input_manifest_required`
- `actual_closure_ready`: `False`
- `ready_component_count`: `0`
- `blocked_component_count`: `6`
- `remaining_evidence`: `engine_input_manifest`, `engine_runtime`, `engine_run_slots`, `adapter_rows`, `per_engine_run_receipts`, `external_receipts`

| Component | Status | Pass | Current | Required | Blockers |
|---|---|---|---|---|---|
| `engine_input_manifest` | `blocked` | `False` | `{"blocked_case_input_slot_count": 12, "input_manifest_detected": false, "input_manifest_row_count": 0, "input_manifest_status": "not_detected", "required_case_count": 12, "template_manifest_ready": false, "template_missing_local_file_count": 48, "template_missing_receipt_ref_count": 60, "template_preflight_status": "operator_manifest_completion_required"}` | `{"blocked_case_input_slot_count": 0, "input_manifest_detected": true, "input_manifest_row_count": ">=12"}` | `public_benchmark_vina_gnina_input_manifest_not_detected`, `public_benchmark_vina_gnina_case_inputs_incomplete` |
| `engine_runtime` | `blocked` | `False` | `{"available_engine_count": 0, "missing_engine_count": 2, "missing_engine_ids": ["vina", "gnina"], "runtime_ready_for_engine_execution": false, "runtime_status": "execution_plan_blocked"}` | `{"missing_engine_count": 0, "runtime_ready_for_engine_execution": true}` | `vina_gnina_execution_plan_not_ready`, `vina_binary_missing`, `gnina_binary_missing` |
| `engine_run_slots` | `blocked` | `False` | `{"blocked_engine_run_slot_count": 24, "ready_engine_run_slot_count": 0, "required_engine_run_count": 24}` | `{"blocked_engine_run_slot_count": 0, "ready_engine_run_slot_count": 24}` | `public_benchmark_vina_gnina_engine_run_slots_incomplete` |
| `adapter_rows` | `blocked` | `False` | `{"adapter_case_count": 0, "adapter_preflight_contract_pass": false, "adapter_preflight_status": "missing", "adapter_rows_ready": false, "detected_row_artifact_count": 0, "row_candidate_status": "row_artifact_missing", "selected_row_count": 0}` | `{"adapter_case_count": ">=1", "adapter_preflight_contract_pass": true, "detected_row_artifact_count": ">=1"}` | `public_benchmark_vina_gnina_rows_not_detected`, `vina_gnina_rows_not_provided` |
| `per_engine_run_receipts` | `blocked` | `False` | `{"adapter_template_ready": false, "expected_rows_detected": false, "missing_engine_run_receipt_value_count": 72, "role_receipt_blocked_count": 72, "role_receipt_plan_count": 96, "rows_template_preflight_status": "operator_rows_completion_required"}` | `{"adapter_template_ready": true, "expected_rows_detected": true, "role_receipt_blocked_count": 0}` | `public_benchmark_vina_gnina_engine_run_receipts_incomplete` |
| `external_receipts` | `blocked` | `False` | `{"all_expected_artifact_roles_complete": false, "blocked_official_receipt_role_count": 1, "external_receipt_completion_status": "blocked_pending_vina_gnina_receipts", "missing_expected_artifact_roles": ["vina_gnina_comparison_adapter"]}` | `{"all_expected_artifact_roles_complete": true, "blocked_official_receipt_role_count": 0}` | `vina_gnina_rows_not_provided`, `public_benchmark_external_receipt_role_missing:vina_gnina_comparison_adapter`, `public_benchmark_vina_gnina_input_manifest_not_detected`, `public_benchmark_vina_gnina_engine_runtime_not_ready` |

### Public Benchmark Source Access Preflight

- `receipt_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json`
- `receipt_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md`
- `network_probe_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`
- `receipt_status`: `reachable`
- `receipt_reachable_count`: `6`
- `external_receipts_status`: `operator_receipts_required`
- `external_receipts_complete_roles`: `2/3`

| Source | Access Mode | Primary Probe |
| --- | --- | --- |
| `pdbbind_plus_casf` | `operator_download_and_license_or_accession_receipt_required` | `curl --head --location --max-time 20 'https://www.pdbbind-plus.org.cn/casf'` |
| `dud_e` | `public_download_with_operator_checksum_receipt` | `curl --head --location --max-time 20 'https://dude.docking.org/targets/'` |
| `lit_pcba` | `public_download_with_operator_checksum_receipt` | `curl --head --location --max-time 20 'https://drugdesign.unistra.fr/LIT-PCBA/'` |
| `autodock_vina` | `engine_install_and_run_receipt_required` | `curl --head --location --max-time 20 'https://vina.scripps.edu/'` |
| `gnina` | `engine_install_and_run_receipt_required` | `curl --head --location --max-time 20 'https://github.com/gnina/gnina'` |
| `posebusters` | `reference_checklist_or_tool_run_receipt_required` | `curl --head --location --max-time 20 'https://github.com/maabuu/posebusters'` |

## Provided Closure Evidence

### GPCR Phase 3 Gate

- `status`: `ready`
- `actual_closure_ready`: `True`
- `target_pass_count`: `3/3`

| Target | PR-AUC CI Low | Top20 Hit Rate | Decoys Above Positive | Out-Anchored | Status |
| --- | --- | --- | --- | --- | --- |
| `DRD2` | `1.0` | `0.6` | `0` | `False` | `pass` |
| `HTR2A` | `1.0` | `0.6` | `0` | `False` | `pass` |
| `OPRM1` | `1.0` | `0.6` | `0` | `False` | `pass` |

## Upstream Source Blockers

- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_rows_not_acquired`
- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_engine_runtime_not_ready`
- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_input_manifest_not_detected`
- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_engine_binaries_or_container_images_missing`
- `public_benchmark_phase2_source_acquisition::public_benchmark_external_receipts_not_attached`
- `pocketmd_lite_source_acquisition::pocketmd_lite_topk_rows_not_acquired`
- `pocketmd_lite_source_acquisition::upstream_top_k_candidate_receipts_not_attached`
- `pocketmd_lite_source_acquisition::lite_refinement_metric_receipts_not_attached`

## Materialization

```bash
python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked
```

## Claim Boundary

This handoff is an operator checklist derived from the science row audit. It is not actual science evidence and does not close Phase 2, GPCR hard-decoy, or PocketMD Lite gates without accepted real rows.
