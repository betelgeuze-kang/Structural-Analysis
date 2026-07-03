# Science Actual Closure Operator Handoff

- `status`: `operator_rows_required`
- `contract_pass`: `True`
- `science_actual_closure_contract_pass`: `False`
- `missing_slot_count`: `2`
- `slot_count`: `6`

| Row Input | Status | Preferred Path | CSV Starter | Closes Criteria | Action |
| --- | --- | --- | --- | --- | --- |
| `subset_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `casf_pdbbind_pose_success_harness_ready` | `review_subset_rows_materialization` |
| `pose_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `review_pose_rows_materialization` |
| `enrichment_rows` | `provided` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `dud_e_or_lit_pcba_enrichment_ready` | `review_enrichment_rows_materialization` |
| `vina_gnina_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `vina_gnina_comparison_ready` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |
| `gpcr_rows` | `provided` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `review_gpcr_rows_materialization` |
| `pocketmd_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved, broad_all_atom_fep_claims_locked` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` |

## Missing Row Packet

| Row Input | Action | Template | Materialization |
| --- | --- | --- | --- |
| `vina_gnina_rows` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked` |

### Vina/GNINA Engine Run Slots

- `blocked_engine_run_slot_count`: `24`

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

| Slot | Case | Rank | Status | Action |
| --- | --- | --- | --- | --- |
| `pocketmd_lite_case_001_rank_01` | `pocketmd_lite_case_001` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01` |
| `pocketmd_lite_case_001_rank_02` | `pocketmd_lite_case_001` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_02` |
| `pocketmd_lite_case_002_rank_01` | `pocketmd_lite_case_002` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_002_rank_01` |
| `pocketmd_lite_case_002_rank_02` | `pocketmd_lite_case_002` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_002_rank_02` |
| `pocketmd_lite_case_003_rank_01` | `pocketmd_lite_case_003` | `1` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_003_rank_01` |
| `pocketmd_lite_case_003_rank_02` | `pocketmd_lite_case_003` | `2` | `missing` | `attach_pocketmd_topk_row_for_pocketmd_lite_case_003_rank_02` |

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
