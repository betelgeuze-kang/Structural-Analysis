# PocketMD Lite Top-K Survival Report

- `status`: `operator_evidence_required`
- `contract_pass`: `False`
- `product_surface_ready`: `False`
- `real_refinement_case_count`: `0`
- `top_k_candidate_count`: `0`
- `phase4_exit_gate`: `blocked`
- `failed_criteria`: `top_k_refinement_rows_present, top_k_refinement_case_coverage, local_min_survival_materialized, contact_persistence_materialized, h_bond_persistence_materialized, clash_relief_materialized, uncertainty_summary_materialized, report_blockers_resolved`
- `first_blocked_target`: `top_k_refinement_operator_intake`
- `first_blocker`: `pocketmd_lite_topk_candidate_rows_missing`

| Metric | Current | Required |
|---|---|---|
| `local_min_survival_rate` | `missing` | `present` |
| `contact_persistence_rate_median` | `missing` | `present` |
| `h_bond_persistence_rate_median` | `missing` | `present` |
| `clash_relief_rate` | `missing` | `present` |
| `uncertainty_width_median` | `missing` | `present` |

| Criterion | Pass | Current | Required | Blockers |
|---|---|---|---|---|
| `top_k_refinement_rows_present` | `False` | `0` | `>=6` | `pocketmd_lite_topk_candidate_rows_missing` |
| `top_k_refinement_case_coverage` | `False` | `False` | `True` | `pocketmd_lite_topk_candidate_rows_missing` |
| `local_min_survival_materialized` | `False` | `missing` | `present` | `pocketmd_lite_local_min_survival_rows_missing` |
| `contact_persistence_materialized` | `False` | `missing` | `present` | `pocketmd_lite_contact_persistence_rows_missing` |
| `h_bond_persistence_materialized` | `False` | `missing` | `present` | `pocketmd_lite_h_bond_persistence_rows_missing` |
| `clash_relief_materialized` | `False` | `missing` | `present` | `pocketmd_lite_clash_relief_rows_missing` |
| `uncertainty_summary_materialized` | `False` | `missing` | `present` | `pocketmd_lite_uncertainty_rows_missing` |
| `report_blockers_resolved` | `False` | `False` | `True` | `pocketmd_lite_topk_candidate_rows_missing, pocketmd_lite_local_min_survival_rows_missing, pocketmd_lite_contact_persistence_rows_missing, pocketmd_lite_h_bond_persistence_rows_missing, pocketmd_lite_clash_relief_rows_missing, pocketmd_lite_uncertainty_rows_missing` |
| `broad_all_atom_fep_claims_locked` | `True` | `True` | `True` | `none` |

| Case | Candidates | Top-K Ranks | Local-Min Survival | Contact Median | H-Bond Median | Clash Relief | Uncertainty Median |
|---|---|---|---|---|---|---|---|

## Top-K Row Quality

- `contract_pass`: `False`
- `minimums`: `{'min_real_refinement_case_count': 3, 'min_candidate_count_per_case': 2, 'min_top_k_rank_coverage_per_case': 2, 'min_total_top_k_candidate_count': 6}`
- `rank_policy`: `For each case, supplied ranks must form a contiguous prefix starting at rank 1; cherry-picked gaps are not valid top-k refinement input.`
- `scope_policy`: `PocketMD Lite refinement rows are bounded to upstream top-k candidates only; top_k_rank must be between 1 and 20.`

## Operator Next Actions

- `materialize_pocketmd_lite_operator_intake_from_rows`
- `fill_pocketmd_lite_operator_intake_packet`
- `attach_top_k_candidate_refinement_rows`
- `run_pocketmd_lite_topk_survival_materializer`
- `compute_contact_and_h_bond_persistence`
- `compute_clash_relief_and_uncertainty_summary`
- `regenerate_pocketmd_lite_science_product_surface`

This report is a seed shape for PocketMD Lite evidence. With zero real refinement rows it is intentionally blocked and cannot support a product claim.
