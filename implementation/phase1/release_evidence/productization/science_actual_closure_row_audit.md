# Science Actual Closure Row Audit

- `status`: `operator_evidence_required`
- `contract_pass`: `False`
- `component_ready_count`: `1/3`
- `requirement_pass_count`: `10/19`
- `completion_audit_status`: `operator_evidence_required`
- `missing_row_inputs`: `vina_gnina_rows, pocketmd_rows`
- `upstream_source_blockers`: `public_benchmark_phase2_source_acquisition::public_benchmark_vina_gnina_rows_not_acquired, public_benchmark_phase2_source_acquisition::public_benchmark_external_receipts_not_attached, pocketmd_lite_source_acquisition::pocketmd_lite_topk_rows_not_acquired, pocketmd_lite_source_acquisition::upstream_top_k_candidate_receipts_not_attached, pocketmd_lite_source_acquisition::lite_refinement_metric_receipts_not_attached`

| Completion Component | Status | Requirements | Missing Row Inputs | Failed Criteria |
|---|---|---|---|---|
| `public_benchmark_phase2_actual_closure` | `operator_rows_required` | `4/5` | `vina_gnina_rows` | `vina_gnina_comparison_ready` |
| `gpcr_hard_decoy_actual_closure` | `complete` | `5/5` | `none` | `none` |
| `pocketmd_lite_topk_actual_closure` | `operator_rows_required` | `1/9` | `pocketmd_rows` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved` |

| Row Input | Status | Component | Closes Criteria | Default Path |
|---|---|---|---|---|
| `subset_rows` | `provided` | `public_benchmark_phase2_actual_closure` | `casf_pdbbind_pose_success_harness_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `provided` | `public_benchmark_phase2_actual_closure` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `provided` | `public_benchmark_phase2_actual_closure` | `dud_e_or_lit_pcba_enrichment_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `missing` | `public_benchmark_phase2_actual_closure` | `vina_gnina_comparison_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |
| `gpcr_rows` | `provided` | `gpcr_hard_decoy_actual_closure` | `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` |
| `pocketmd_rows` | `missing` | `pocketmd_lite_topk_actual_closure` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved, broad_all_atom_fep_claims_locked` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` |

| Component | Status | Failed Criteria | Blocker Count |
|---|---|---|---|
| `public_benchmark_phase2_actual_closure` | `operator_evidence_required` | `vina_gnina_comparison_ready` | `1` |
| `gpcr_hard_decoy_actual_closure` | `ready` | `none` | `0` |
| `pocketmd_lite_topk_actual_closure` | `operator_evidence_required` | `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved` | `13` |

- `operator_next_actions`: `attach_vina_gnina_rows, attach_pocketmd_rows, resolve_public_benchmark_phase2_source_acquisition_blockers, resolve_pocketmd_lite_source_acquisition_blockers, run_science_actual_closure_row_materializer, review_science_actual_closure_row_audit`

This runner only materializes operator-attached raw rows through the existing Public Benchmark, GPCR, and PocketMD Lite materializers. It does not download benchmark data, generate docking scores, run MD, infer missing metrics, or treat fixture/proxy rows as actual science closure evidence.
