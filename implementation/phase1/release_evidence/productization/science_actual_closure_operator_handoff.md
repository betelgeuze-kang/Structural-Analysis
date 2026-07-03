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

## Upstream Source Blockers

- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_rows_not_acquired`
- `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_engine_inputs_not_ready`
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
