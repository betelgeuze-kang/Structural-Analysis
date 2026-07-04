# PocketMD Lite Top-K Survival Report

- `status`: `ready`
- `contract_pass`: `True`
- `product_surface_ready`: `True`
- `real_refinement_case_count`: `3`
- `top_k_candidate_count`: `6`
- `phase4_exit_gate`: `ready`
- `failed_criteria`: `none`
- `first_blocked_target`: `none`
- `first_blocker`: `none`

| Metric | Current | Required |
|---|---|---|
| `local_min_survival_rate` | `1.0` | `present` |
| `contact_persistence_rate_median` | `0.7218705000000001` | `present` |
| `h_bond_persistence_rate_median` | `1.0` | `present` |
| `clash_relief_rate` | `0.0` | `present` |
| `uncertainty_width_median` | `5.700850500000001` | `present` |

| Criterion | Pass | Current | Required | Blockers |
|---|---|---|---|---|
| `top_k_refinement_rows_present` | `True` | `6` | `>=6` | `none` |
| `top_k_refinement_case_coverage` | `True` | `True` | `True` | `none` |
| `local_min_survival_materialized` | `True` | `1.0` | `present` | `none` |
| `contact_persistence_materialized` | `True` | `0.7218705000000001` | `present` | `none` |
| `h_bond_persistence_materialized` | `True` | `1.0` | `present` | `none` |
| `clash_relief_materialized` | `True` | `0.0` | `present` | `none` |
| `uncertainty_summary_materialized` | `True` | `5.700850500000001` | `present` | `none` |
| `report_blockers_resolved` | `True` | `True` | `True` | `none` |
| `broad_all_atom_fep_claims_locked` | `True` | `True` | `True` | `none` |

## Top-K Refinement Completion Audit

- `status`: `pass`
- `pass`: `True`
- `requirement_pass_count`: `10/10`

| Requirement | Status | Blockers |
|---|---|---|
| `operator_input_source_receipt_pass` | `pass` | `none` |
| `top_k_refinement_rows_present` | `pass` | `none` |
| `top_k_refinement_case_coverage` | `pass` | `none` |
| `local_min_survival_materialized` | `pass` | `none` |
| `contact_persistence_materialized` | `pass` | `none` |
| `h_bond_persistence_materialized` | `pass` | `none` |
| `clash_relief_materialized` | `pass` | `none` |
| `uncertainty_summary_materialized` | `pass` | `none` |
| `report_blockers_resolved` | `pass` | `none` |
| `broad_all_atom_fep_claims_locked` | `pass` | `none` |

| Case | Candidates | Top-K Ranks | Local-Min Survival | Contact Median | H-Bond Median | Clash Relief | Uncertainty Median |
|---|---|---|---|---|---|---|---|
| `pocketmd_lite_case_001` | `2` | `1, 2` | `1.0` | `0.862069` | `1.0` | `0.0` | `7.286529000000005` |
| `pocketmd_lite_case_002` | `2` | `1, 2` | `1.0` | `0.707265` | `1.0` | `0.0` | `3.6382495000000077` |
| `pocketmd_lite_case_003` | `2` | `1, 2` | `1.0` | `0.6833400000000001` | `1.0` | `0.0` | `3.7000224999999958` |

## Top-K Row Quality

- `contract_pass`: `True`
- `minimums`: `{'min_real_refinement_case_count': 3, 'min_candidate_count_per_case': 2, 'min_top_k_rank_coverage_per_case': 2, 'min_total_top_k_candidate_count': 6}`
- `rank_policy`: `For each case, supplied ranks must form a contiguous prefix starting at rank 1; cherry-picked gaps are not valid top-k refinement input.`
- `scope_policy`: `PocketMD Lite refinement rows are bounded to upstream top-k candidates only; top_k_rank must be between 1 and 20.`

## Operator Next Actions

- `review_pocketmd_lite_topk_survival_report`
- `regenerate_pocketmd_lite_science_product_surface`
- `regenerate_pm_release_gate_report`

This report materializes bounded PocketMD Lite evidence from operator-attached top-k refinement rows. It does not run MD, create candidate rows, infer FEP, or unlock broad all-atom dynamics claims.
