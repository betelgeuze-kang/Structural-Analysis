# GPCR Hard-Decoy Suite Report

- `status`: `ready`
- `contract_pass`: `True`
- `broad_gpcr_family_claim_safe`: `True`
- `target_pass_count`: `3/3`
- `phase3_exit_gate`: `ready`
- `failed_criteria`: `none`
- `first_blocked_target`: `none`
- `first_blocker`: `none`
- `ranking_pr_auc_ci_low_min_observed`: `1.0`
- `top20_hit_rate_min_observed`: `0.6`
- `decoys_above_positive_count_max_observed`: `0`
- `positive_out_anchored_target_count`: `0`

| Criterion | Pass | Required | Failed Targets | Blocker Count |
|---|---|---|---|---|
| `ranking_pr_auc_ci_low_min` | `True` | `>=0.45` | `none` | `0` |
| `top20_hit_rate_min` | `True` | `>=0.2` | `none` | `0` |
| `decoys_above_positive_count_max` | `True` | `<=0` | `none` | `0` |
| `no_positive_out_anchored_by_top_decoys` | `True` | `False` | `none` | `0` |
| `raw_hard_decoy_rows_actual_closure` | `True` | `computed_from_raw_hard_decoy_rows_with_quality_minimums` | `none` | `0` |

| Target | Status | PR AUC CI Low | Top-20 Hit Rate | Decoys Above Positive | Positive Out-Anchored | Blockers |
|---|---|---|---|---|---|---|
| `DRD2` | `pass` | `1.0` | `0.6` | `0` | `False` | `none` |
| `HTR2A` | `pass` | `1.0` | `0.6` | `0` | `False` | `none` |
| `OPRM1` | `pass` | `1.0` | `0.6` | `0` | `False` | `none` |

## Phase 3 Completion Audit

- `status`: `pass`
- `pass`: `True`
- `requirement_pass_count`: `8/8`

| Requirement | Status | Blockers |
|---|---|---|
| `expected_target_set_complete` | `pass` | `none` |
| `operator_input_source_receipt_pass` | `pass` | `none` |
| `all_target_rows_contract_pass` | `pass` | `none` |
| `ranking_pr_auc_ci_low_min` | `pass` | `none` |
| `top20_hit_rate_min` | `pass` | `none` |
| `decoys_above_positive_count_max` | `pass` | `none` |
| `no_positive_out_anchored_by_top_decoys` | `pass` | `none` |
| `raw_hard_decoy_rows_actual_closure` | `pass` | `none` |

## Operator Next Actions


This report evaluates operator-attached DRD2/HTR2A/OPRM1 hard-decoy metrics against the Phase 3 exit criteria. It does not infer target activity, generate docking results, or unlock broad GPCR claims without all required numeric receipts.
