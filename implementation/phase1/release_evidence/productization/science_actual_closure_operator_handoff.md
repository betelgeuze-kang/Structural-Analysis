# Science Actual Closure Operator Handoff

- `status`: `operator_rows_required`
- `contract_pass`: `True`
- `science_actual_closure_contract_pass`: `False`
- `missing_slot_count`: `6`
- `slot_count`: `6`

| Row Input | Status | Preferred Path | Closes Criteria | Action |
| --- | --- | --- | --- | --- |
| `subset_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` | `casf_pdbbind_pose_success_harness_ready` | `attach_subset_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `attach_pose_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` | `dud_e_or_lit_pcba_enrichment_ready` | `attach_enrichment_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `vina_gnina_comparison_ready` | `attach_vina_gnina_rows_at_implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |
| `gpcr_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `attach_gpcr_rows_at_implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` |
| `pocketmd_rows` | `operator_input_required` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved, broad_all_atom_fep_claims_locked` | `attach_pocketmd_rows_at_implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` |

## Materialization

```bash
python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked
```

## Claim Boundary

This handoff is an operator checklist derived from the science row audit. It is not actual science evidence and does not close Phase 2, GPCR hard-decoy, or PocketMD Lite gates without accepted real rows.
