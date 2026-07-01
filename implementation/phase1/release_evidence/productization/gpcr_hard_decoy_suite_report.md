# GPCR Hard-Decoy Suite Report

- `status`: `locked`
- `contract_pass`: `False`
- `broad_gpcr_family_claim_safe`: `False`
- `target_pass_count`: `0/3`
- `phase3_exit_gate`: `blocked`
- `failed_criteria`: `ranking_pr_auc_ci_low_min, top20_hit_rate_min, decoys_above_positive_count_max, no_positive_out_anchored_by_top_decoys, raw_hard_decoy_rows_actual_closure`
- `first_blocked_target`: `DRD2`
- `first_blocker`: `DRD2:hard_decoy_rows_required_for_actual_closure`

| Criterion | Pass | Required | Failed Targets | Blocker Count |
|---|---|---|---|---|
| `ranking_pr_auc_ci_low_min` | `False` | `>=0.45` | `DRD2, HTR2A, OPRM1` | `3` |
| `top20_hit_rate_min` | `False` | `>=0.2` | `DRD2, HTR2A, OPRM1` | `3` |
| `decoys_above_positive_count_max` | `False` | `<=0` | `DRD2, HTR2A, OPRM1` | `3` |
| `no_positive_out_anchored_by_top_decoys` | `False` | `False` | `DRD2, HTR2A, OPRM1` | `3` |
| `raw_hard_decoy_rows_actual_closure` | `False` | `computed_from_raw_hard_decoy_rows_with_quality_minimums` | `DRD2, HTR2A, OPRM1` | `3` |

| Target | Status | PR AUC CI Low | Top-20 Hit Rate | Decoys Above Positive | Positive Out-Anchored | Blockers |
|---|---|---|---|---|---|---|
| `DRD2` | `blocked` | `missing` | `missing` | `missing` | `missing` | `DRD2:hard_decoy_rows_required_for_actual_closure, DRD2:ranking_pr_auc_ci_low_required, DRD2:top20_hit_rate_required, DRD2:decoys_above_positive_count_required, DRD2:positive_out_anchored_by_top_decoys_required` |
| `HTR2A` | `blocked` | `missing` | `missing` | `missing` | `missing` | `HTR2A:hard_decoy_rows_required_for_actual_closure, HTR2A:ranking_pr_auc_ci_low_required, HTR2A:top20_hit_rate_required, HTR2A:decoys_above_positive_count_required, HTR2A:positive_out_anchored_by_top_decoys_required` |
| `OPRM1` | `blocked` | `missing` | `missing` | `missing` | `missing` | `OPRM1:hard_decoy_rows_required_for_actual_closure, OPRM1:ranking_pr_auc_ci_low_required, OPRM1:top20_hit_rate_required, OPRM1:decoys_above_positive_count_required, OPRM1:positive_out_anchored_by_top_decoys_required` |

## Operator Next Actions

- `drd2_hard_decoy_metrics`: fill DRD2 hard-decoy metrics in the GPCR operator intake packet
- `htr2a_hard_decoy_metrics`: fill HTR2A hard-decoy metrics in the GPCR operator intake packet
- `oprm1_hard_decoy_metrics`: fill OPRM1 hard-decoy metrics in the GPCR operator intake packet

This report evaluates operator-attached DRD2/HTR2A/OPRM1 hard-decoy metrics against the Phase 3 exit criteria. It does not infer target activity, generate docking results, or unlock broad GPCR claims without all required numeric receipts.
