# Science Actual Closure Row Audit

- `status`: `operator_evidence_required`
- `contract_pass`: `False`
- `component_ready_count`: `0/3`
- `requirement_pass_count`: `1/19`
- `missing_row_inputs`: `subset_rows, pose_rows, enrichment_rows, vina_gnina_rows, gpcr_rows, pocketmd_rows`

| Row Input | Status | Component | Closes Criteria | Default Path |
|---|---|---|---|---|
| `subset_rows` | `missing` | `public_benchmark_phase2_actual_closure` | `casf_pdbbind_pose_success_harness_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `missing` | `public_benchmark_phase2_actual_closure` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `missing` | `public_benchmark_phase2_actual_closure` | `dud_e_or_lit_pcba_enrichment_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `missing` | `public_benchmark_phase2_actual_closure` | `vina_gnina_comparison_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |
| `gpcr_rows` | `missing` | `gpcr_hard_decoy_actual_closure` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` |
| `pocketmd_rows` | `missing` | `pocketmd_lite_topk_actual_closure` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved, broad_all_atom_fep_claims_locked` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` |

| Component | Status | Failed Criteria | Blocker Count |
|---|---|---|---|
| `public_benchmark_phase2_actual_closure` | `operator_evidence_required` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready, vina_gnina_comparison_ready, dud_e_or_lit_pcba_enrichment_ready` | `6` |
| `gpcr_hard_decoy_actual_closure` | `operator_evidence_required` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `15` |
| `pocketmd_lite_topk_actual_closure` | `operator_evidence_required` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved` | `13` |

- `operator_next_actions`: `attach_subset_rows, attach_pose_rows, attach_enrichment_rows, attach_vina_gnina_rows, attach_gpcr_rows, attach_pocketmd_rows, run_science_actual_closure_row_materializer, review_science_actual_closure_row_audit`

This runner only materializes operator-attached raw rows through the existing Public Benchmark, GPCR, and PocketMD Lite materializers. It does not download benchmark data, generate docking scores, run MD, infer missing metrics, or treat fixture/proxy rows as actual science closure evidence.
